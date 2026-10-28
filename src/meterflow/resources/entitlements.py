"""Entitlements — ask BEFORE doing the work.

``check()`` is where a hard limit says no; recording usage afterwards never blocks, so an app that
skips this call gets no enforcement at all — only an honest ledger.

``allowed: False`` is a normal answer, not an error: the call returns and ``reason`` says why
(``no_subscription``, ``not_in_plan``, ``hard_limit_reached``, ``insufficient_credits``). A feature
key the project does not know at all is a 404 → ``NotFoundError``, because that is a typo, not a plan.

Answers are reused for the ``Cache-Control: max-age`` the API sends (15 s), per customer, feature and
quantity, unless ``entitlements_cache=False``. A usage record, grant or deduct for a customer makes
their answers stale. While MeterFlow is unreachable, a call returns its last answer with
``stale: True``, or else ``check()`` returns the ``entitlement_defaults`` entry for the feature.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, TypedDict

import httpx

from .._entitlement_cache import CacheRead, EntitlementFallbackContext, is_outage, max_age_seconds
from .._http import RequestSpec, encode_path_segment
from ..types import EntitlementReason, EntitlementsResponse, FeatureType

if TYPE_CHECKING:
    from ..client import AsyncMeterFlow, MeterFlow, _BaseClient


class _EntitlementCheckRequired(TypedDict):
    feature: str
    feature_type: FeatureType | None
    allowed: bool


class EntitlementCheck(_EntitlementCheckRequired, total=False):
    """What ``check()`` returns: the API's ``EntitlementResponse``, or a fallback while MeterFlow is unreachable.

    ``stale: True`` marks the last answer reused past its ``max-age``; ``reason: "offline_default"`` marks
    your ``entitlement_defaults`` entry, which knows nothing of the plan, so its ``feature_type`` is None.
    The other keys are ``EntitlementResponse``'s, repeated because a generated type cannot be widened.
    """

    reason: EntitlementReason | Literal["offline_default"] | None
    limit_type: str | None
    included: int | None
    used: str | None
    remaining: str | None
    period_start: str | None
    period_end: str | None
    stale: bool


class EntitlementList(EntitlementsResponse, total=False):
    """What ``get()`` returns: the API's answer, with ``stale: True`` when it is the last one reused during an outage."""

    stale: bool


def get_spec(customer_id: str) -> RequestSpec:
    return RequestSpec("GET", f"entitlements/{encode_path_segment(customer_id)}")


def check_spec(customer_id: str, feature: str, quantity: int | None) -> RequestSpec:
    return RequestSpec("GET", f"entitlements/{encode_path_segment(customer_id)}/check", query={"feature": feature, "quantity": quantity})


def _get_key(customer_id: str) -> str:
    return f"get\0{customer_id}"


def _check_key(customer_id: str, feature: str, quantity: int | None) -> str:
    return f"check\0{customer_id}\0{feature}\0{quantity or 1}"


class _Answer:
    """One entitlements call's cache handling, shared by the sync and async resources, which only differ in how they wait.

    client: the client whose cache and options apply.
    key: the call's cache key.
    customer_id: the customer the call is for.
    feature: the feature checked; None for ``get()``, which has no default.
    """

    def __init__(self, client: _BaseClient, key: str, customer_id: str, feature: str | None) -> None:
        self._client = client
        self._key = key
        self._customer_id = customer_id
        self._feature = feature
        self._max_age = 0
        self.cached: CacheRead | None = client.entitlement_cache.read(key) if client.entitlement_cache is not None else None

    def read_headers(self, headers: httpx.Headers) -> None:
        """Note the response's ``max-age``.

        headers: the successful response's headers.
        """
        self._max_age = max_age_seconds(headers.get("cache-control"))

    def keep(self, value: Any) -> Any:
        """Store a fresh answer for its ``max-age``, and return it.

        value: the API's answer.
        """
        if self._client.entitlement_cache is not None:
            self._client.entitlement_cache.write(self._key, self._customer_id, value, self._max_age)
        return value

    def fallback(self, error: Exception) -> Any:
        """The answer for a failed call: the last one marked stale, else the feature's default.

        Re-raises ``error`` when it was an answer rather than an outage, or when there is nothing to fall back on.

        error: what the call raised.
        """
        if not is_outage(error):
            raise error
        if self.cached is not None:
            self._tell(error, "stale")
            return {**self.cached.value, "stale": True}
        default = None if self._feature is None else self._offline_default(self._feature)
        if default is None:
            raise error
        self._tell(error, "default")
        return default

    def _offline_default(self, feature: str) -> EntitlementCheck | None:
        """The configured answer for a feature: its own entry, else ``"*"``; None when neither is set.

        feature: the feature checked.
        """
        defaults = self._client.options.entitlement_defaults
        setting = defaults.get(feature, defaults.get("*"))
        if setting is None:
            return None
        return {"feature": feature, "feature_type": None, "allowed": setting == "allow", "reason": "offline_default"}

    def _tell(self, error: Exception, fallback: Literal["stale", "default"]) -> None:
        """Hand the error and the fallback to ``on_error``, ignoring anything it raises: it is the caller's code.

        error: what the call raised.
        fallback: what the call answers with instead.
        """
        on_error: Callable[[Exception, EntitlementFallbackContext], None] | None = self._client.options.on_error
        if on_error is None:
            return
        try:
            on_error(error, EntitlementFallbackContext(self._customer_id, self._feature, fallback))
        except Exception:  # noqa: S110 — the hook is the caller's; its failure must not undo the fallback
            pass


class EntitlementsResource:
    def __init__(self, client: MeterFlow) -> None:
        self._client = client

    def get(self, customer_id: str) -> EntitlementList:
        """Every feature on the customer's plan, with this period's usage; a metered row answers for the next unit, as ``check()`` would.

        Empty ``entitlements`` without a subscription.
        customer_id: the customer asked about.
        """
        return self._answer(_Answer(self._client, _get_key(customer_id), customer_id, None), get_spec(customer_id))  # type: ignore[no-any-return]

    def check(self, customer_id: str, feature: str, *, quantity: int | None = None) -> EntitlementCheck:
        """May this customer use ``feature`` (``quantity`` more units of it — "may they do 5 more?") right now?

        customer_id: the customer asked about.
        feature: a meter's event name or a plan feature key.
        quantity: how many more units the app is about to use; 1 on the server when None.
        """
        answer = _Answer(self._client, _check_key(customer_id, feature, quantity), customer_id, feature)
        return self._answer(answer, check_spec(customer_id, feature, quantity))  # type: ignore[no-any-return]

    def _answer(self, answer: _Answer, spec: RequestSpec) -> Any:
        """Return the fresh cached answer, else the API's, else a fallback.

        answer: the call's cache handling.
        spec: the request to make when nothing fresh is cached.
        """
        if answer.cached is not None and answer.cached.fresh:
            return answer.cached.value
        try:
            return answer.keep(self._client.request(spec, answer.read_headers))
        except Exception as error:
            return answer.fallback(error)


class AsyncEntitlementsResource:
    def __init__(self, client: AsyncMeterFlow) -> None:
        self._client = client

    async def get(self, customer_id: str) -> EntitlementList:
        """Every feature on the customer's plan, with this period's usage; a metered row answers for the next unit, as ``check()`` would.

        Empty ``entitlements`` without a subscription.
        customer_id: the customer asked about.
        """
        return await self._answer(_Answer(self._client, _get_key(customer_id), customer_id, None), get_spec(customer_id))  # type: ignore[no-any-return]

    async def check(self, customer_id: str, feature: str, *, quantity: int | None = None) -> EntitlementCheck:
        """May this customer use ``feature`` (``quantity`` more units of it — "may they do 5 more?") right now?

        customer_id: the customer asked about.
        feature: a meter's event name or a plan feature key.
        quantity: how many more units the app is about to use; 1 on the server when None.
        """
        answer = _Answer(self._client, _check_key(customer_id, feature, quantity), customer_id, feature)
        return await self._answer(answer, check_spec(customer_id, feature, quantity))  # type: ignore[no-any-return]

    async def _answer(self, answer: _Answer, spec: RequestSpec) -> Any:
        """Return the fresh cached answer, else the API's, else a fallback.

        answer: the call's cache handling.
        spec: the request to make when nothing fresh is cached.
        """
        if answer.cached is not None and answer.cached.fresh:
            return answer.cached.value
        try:
            return answer.keep(await self._client.request(spec, answer.read_headers))
        except Exception as error:
            return answer.fallback(error)
