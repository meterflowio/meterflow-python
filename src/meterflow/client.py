"""``MeterFlow`` (sync) and ``AsyncMeterFlow`` — same options, same resources, same errors.

Resources describe a call as a ``RequestSpec``; the client executes it with retries. Everything that
does not depend on *how* you wait lives in ``_http.py`` and ``_retry.py``, so the two clients are
thin and cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from itertools import count
from types import TracebackType
from typing import Any

import httpx

from ._entitlement_cache import EntitlementCache, EntitlementDefault, OnEntitlementError
from ._http import RequestSpec, _async_sleep, _sleep, decode_response, map_response_error, request_kwargs
from ._retry import RetryPolicy
from .resources.credits import AsyncCreditsResource, CreditsResource
from .resources.entitlements import AsyncEntitlementsResource, EntitlementsResource
from .resources.plans import AsyncPlansResource, PlansResource
from .resources.portal import AsyncPortalResource, PortalResource
from .resources.subscriptions import AsyncSubscriptionsResource, SubscriptionsResource
from .resources.usage import AsyncUsageResource, UsageResource
from .resources.webhooks import AsyncWebhooksResource, WebhooksResource

DEFAULT_BASE_URL = "https://api.meter-flow.com/api/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_RETRIES = 3
KEY_PREFIXES = ("mf_live_", "mf_test_")


@dataclass(frozen=True)
class ClientOptions:
    """The resolved configuration — what the Node SDK exposes as ``client.options``."""

    api_key: str
    base_url: str
    timeout: float
    retries: int
    entitlements_cache: bool = True
    entitlement_defaults: Mapping[str, EntitlementDefault] = field(default_factory=dict)
    on_error: OnEntitlementError | None = None


class _BaseClient:
    def __init__(
        self,
        api_key: str,
        base_url: str | None,
        timeout: float | None,
        retries: int | None,
        entitlements_cache: bool,
        entitlement_defaults: Mapping[str, EntitlementDefault] | None,
        on_error: OnEntitlementError | None,
    ) -> None:
        if not api_key.startswith(KEY_PREFIXES):
            raise ValueError("api_key must start with mf_live_ or mf_test_")
        self.options = ClientOptions(
            api_key=api_key,
            base_url=(base_url or DEFAULT_BASE_URL).rstrip("/") + "/",
            timeout=DEFAULT_TIMEOUT_SECONDS if timeout is None else timeout,
            retries=DEFAULT_RETRIES if retries is None else retries,
            entitlements_cache=entitlements_cache,
            entitlement_defaults=dict(entitlement_defaults or {}),
            on_error=on_error,
        )
        self._retry = RetryPolicy(retries=self.options.retries)
        # Internal: the entitlement answers this client has read; None when ``entitlements_cache`` is False.
        self.entitlement_cache = EntitlementCache() if entitlements_cache else None

    def _kwargs(self, spec: RequestSpec) -> dict[str, Any]:
        return request_kwargs(self.options.api_key, spec)


class MeterFlow(_BaseClient):
    """Synchronous client.

    ``transport`` injects an ``httpx`` transport (tests, proxies) — the Python counterpart of the
    Node SDK's ``fetch`` option. Use it as a context manager or call ``close()`` to release connections.
    ``entitlements_cache``, ``entitlement_defaults`` and ``on_error`` set how ``entitlements`` caches its
    answers and what it answers while MeterFlow is unreachable (``resources/entitlements.py``).
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        transport: httpx.BaseTransport | None = None,
        entitlements_cache: bool = True,
        entitlement_defaults: Mapping[str, EntitlementDefault] | None = None,
        on_error: OnEntitlementError | None = None,
    ) -> None:
        super().__init__(api_key, base_url, timeout, retries, entitlements_cache, entitlement_defaults, on_error)
        self._http = httpx.Client(base_url=self.options.base_url, timeout=self.options.timeout, transport=transport)
        self.credits = CreditsResource(self)
        self.usage = UsageResource(self)
        self.subscriptions = SubscriptionsResource(self)
        self.plans = PlansResource(self)
        self.portal = PortalResource(self)
        self.entitlements = EntitlementsResource(self)
        self.webhooks = WebhooksResource(self)

    def request(self, spec: RequestSpec, on_headers: Callable[[httpx.Headers], None] | None = None) -> Any:
        """Internal — used by resource classes; not part of the public API.

        spec: the call.
        on_headers: given a successful response's headers; how the entitlements cache reads ``Cache-Control``.
        """
        for attempt in count():
            try:
                response = self._http.request(spec.method, spec.path, **self._kwargs(spec))
                if response.is_error:
                    raise map_response_error(response)
                if on_headers is not None:
                    on_headers(response.headers)
                return decode_response(response)
            except Exception as error:
                delay = self._retry.delay_before_retry(attempt, error)
                if delay is None:
                    raise
                _sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover — `count()` never ends

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> MeterFlow:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()


class AsyncMeterFlow(_BaseClient):
    """Asynchronous client — identical surface, every method awaitable. ``async with`` or ``aclose()``."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        entitlements_cache: bool = True,
        entitlement_defaults: Mapping[str, EntitlementDefault] | None = None,
        on_error: OnEntitlementError | None = None,
    ) -> None:
        super().__init__(api_key, base_url, timeout, retries, entitlements_cache, entitlement_defaults, on_error)
        self._http = httpx.AsyncClient(base_url=self.options.base_url, timeout=self.options.timeout, transport=transport)
        self.credits = AsyncCreditsResource(self)
        self.usage = AsyncUsageResource(self)
        self.subscriptions = AsyncSubscriptionsResource(self)
        self.plans = AsyncPlansResource(self)
        self.portal = AsyncPortalResource(self)
        self.entitlements = AsyncEntitlementsResource(self)
        self.webhooks = AsyncWebhooksResource(self)

    async def request(self, spec: RequestSpec, on_headers: Callable[[httpx.Headers], None] | None = None) -> Any:
        """Internal — used by resource classes; not part of the public API.

        spec: the call.
        on_headers: given a successful response's headers; how the entitlements cache reads ``Cache-Control``.
        """
        for attempt in count():
            try:
                response = await self._http.request(spec.method, spec.path, **self._kwargs(spec))
                if response.is_error:
                    raise map_response_error(response)
                if on_headers is not None:
                    on_headers(response.headers)
                return decode_response(response)
            except Exception as error:
                delay = self._retry.delay_before_retry(attempt, error)
                if delay is None:
                    raise
                await _async_sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover — `count()` never ends

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncMeterFlow:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        await self.aclose()
