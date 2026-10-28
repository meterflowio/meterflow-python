"""``entitlements`` resilience: the ``max-age`` cache, the stale and default fallbacks, and ``on_error`` — on both clients.

Mirrors ``sdks/node/tests/resources/entitlements-resilience.test.ts``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from meterflow import AsyncMeterFlow, AuthError, EntitlementFallbackContext, MeterFlow, NotFoundError, RateLimitError, ServerError
from meterflow._entitlement_cache import MAX_CACHED_ENTITLEMENTS, max_age_seconds
from meterflow.resources.entitlements import EntitlementCheck
from meterflow.types import EntitlementResponse
from tests.conftest import FakeApi, api_error

CHECK = "/api/v1/entitlements/cust_1/check"
LIST = "/api/v1/entitlements/cust_1"
CACHEABLE = {"Cache-Control": "private, max-age=15"}

ALLOWED: dict[str, Any] = {"feature": "images.generated", "feature_type": "metered", "allowed": True, "reason": None, "remaining": "380"}
DENIED: dict[str, Any] = {**ALLOWED, "allowed": False, "reason": "hard_limit_reached", "remaining": "0"}
LISTED: dict[str, Any] = {
    "customer_id": "cust_1",
    "environment": "test",
    "subscription_id": "sub-1",
    "plan_id": "plan-1",
    "plan_name": "Pro",
    "period_end": None,
    "entitlements": [ALLOWED],
}


class Clock:
    """The time answers are aged by, stepped by hand."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    frozen = Clock()
    monkeypatch.setattr("meterflow._entitlement_cache._now", frozen)
    return frozen


def answer(api: FakeApi, path: str, body: Any, headers: dict[str, str] | None = None) -> list[httpx.Request]:
    """Answer ``path`` with ``body`` and ``headers`` (cacheable for 15 s by default); return the requests it receives.

    api: the fake API.
    path: the route.
    body: the JSON answered.
    headers: the response headers.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=body, headers=CACHEABLE if headers is None else headers)

    api.on("GET", path, handler)
    return seen


def fail(api: FakeApi, path: str, status: int | None) -> None:
    """Make ``path`` fail: a connection error when ``status`` is None, else that status with the API's error body.

    api: the fake API.
    path: the route.
    status: the error status, or None for a network failure.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if status is None:
            raise httpx.ConnectError("connection refused", request=request)
        return api_error(status, f"failed with {status}")

    api.on("GET", path, handler)


def make(api: FakeApi, **options: Any) -> MeterFlow:
    """A sync client on the fake API with no retries.

    api: the fake API.
    options: the entitlement options to set.
    """
    return MeterFlow("mf_test_abc", retries=0, transport=httpx.MockTransport(api.handle), **options)


def make_async(api: FakeApi, **options: Any) -> AsyncMeterFlow:
    """An async client on the fake API with no retries.

    api: the fake API.
    options: the entitlement options to set.
    """
    return AsyncMeterFlow("mf_test_abc", retries=0, transport=httpx.MockTransport(api.handle_async), **options)


def test_max_age_is_read_from_the_header_and_nothing_else() -> None:
    assert max_age_seconds("private, max-age=15") == 15
    assert max_age_seconds(None) == 0
    assert max_age_seconds("private") == 0
    assert max_age_seconds("no-store, max-age=15") == 0
    assert max_age_seconds("no-cache") == 0


def test_the_check_answer_type_carries_every_key_the_api_sends() -> None:
    """``EntitlementCheck`` repeats ``EntitlementResponse``'s keys to widen two of them; a key the API adds must be added there too."""
    api_keys = EntitlementResponse.__required_keys__ | EntitlementResponse.__optional_keys__
    sdk_keys = EntitlementCheck.__required_keys__ | EntitlementCheck.__optional_keys__
    assert api_keys <= sdk_keys
    assert sdk_keys - api_keys == {"stale"}


# ── The cache ─────────────────────────────────────────────────────────────────


class TestCache:
    def test_a_second_check_inside_max_age_makes_no_request(self, api: FakeApi) -> None:
        seen = answer(api, CHECK, ALLOWED)
        client = make(api)
        client.entitlements.check("cust_1", "images.generated")
        assert client.entitlements.check("cust_1", "images.generated") == ALLOWED
        assert len(seen) == 1

    def test_it_asks_again_once_max_age_has_passed(self, api: FakeApi, clock: Clock) -> None:
        seen = answer(api, CHECK, ALLOWED)
        client = make(api)
        client.entitlements.check("cust_1", "images.generated")
        clock.now += 16
        client.entitlements.check("cust_1", "images.generated")
        assert len(seen) == 2

    def test_its_age_comes_from_the_header(self, api: FakeApi, clock: Clock) -> None:
        seen = answer(api, CHECK, ALLOWED, {"Cache-Control": "private, max-age=60"})
        client = make(api)
        client.entitlements.check("cust_1", "images.generated")
        clock.now += 30
        client.entitlements.check("cust_1", "images.generated")
        assert len(seen) == 1

    def test_nothing_is_cached_without_cache_control(self, api: FakeApi) -> None:
        seen = answer(api, CHECK, ALLOWED, {})
        client = make(api)
        client.entitlements.check("cust_1", "images.generated")
        client.entitlements.check("cust_1", "images.generated")
        assert len(seen) == 2

    def test_a_no_is_cached_as_long_as_a_yes(self, api: FakeApi) -> None:
        seen = answer(api, CHECK, DENIED)
        client = make(api)
        client.entitlements.check("cust_1", "images.generated")
        assert client.entitlements.check("cust_1", "images.generated")["allowed"] is False
        assert len(seen) == 1

    def test_a_feature_a_quantity_and_a_customer_are_kept_apart(self, api: FakeApi) -> None:
        seen = answer(api, CHECK, ALLOWED)
        other = answer(api, "/api/v1/entitlements/cust_2/check", ALLOWED)
        client = make(api)
        client.entitlements.check("cust_1", "images.generated")
        client.entitlements.check("cust_1", "images.generated", quantity=5)
        client.entitlements.check("cust_1", "seats")
        client.entitlements.check("cust_2", "images.generated")
        assert (len(seen), len(other)) == (3, 1)

    def test_get_is_cached_on_its_own_key(self, api: FakeApi) -> None:
        seen = answer(api, LIST, LISTED)
        client = make(api)
        client.entitlements.get("cust_1")
        assert client.entitlements.get("cust_1") == LISTED
        assert len(seen) == 1

    def test_it_is_off_with_entitlements_cache_false(self, api: FakeApi) -> None:
        seen = answer(api, CHECK, ALLOWED)
        client = make(api, entitlements_cache=False)
        client.entitlements.check("cust_1", "images.generated")
        client.entitlements.check("cust_1", "images.generated")
        assert len(seen) == 2
        assert client.entitlement_cache is None

    def test_it_keeps_at_most_the_bound_dropping_the_least_recently_used(self, api: FakeApi) -> None:
        for index in range(MAX_CACHED_ENTITLEMENTS + 1):
            answer(api, f"/api/v1/entitlements/cust_{index}/check", ALLOWED)
        client = make(api)
        for index in range(MAX_CACHED_ENTITLEMENTS + 1):
            client.entitlements.check(f"cust_{index}", "images.generated")
        client.entitlements.check(f"cust_{MAX_CACHED_ENTITLEMENTS}", "images.generated")
        seen = answer(api, "/api/v1/entitlements/cust_0/check", ALLOWED)
        client.entitlements.check("cust_0", "images.generated")
        assert len(seen) == 1

    async def test_the_async_client_caches_too(self, api: FakeApi) -> None:
        seen = answer(api, CHECK, ALLOWED)
        client = make_async(api)
        await client.entitlements.check("cust_1", "images.generated")
        assert await client.entitlements.check("cust_1", "images.generated") == ALLOWED
        assert len(seen) == 1


WRITES: list[tuple[str, str, Callable[[MeterFlow], Any]]] = [
    ("usage.record", "/api/v1/usage/events", lambda client: client.usage.record({"event_name": "x", "customer_external_id": "cust_1"})),
    (
        "usage.record_batch",
        "/api/v1/usage/events/batch",
        lambda client: client.usage.record_batch([{"event_name": "x", "customer_external_id": "cust_1"}]),
    ),
    (
        "credits.grant",
        "/api/v1/credits/grant",
        lambda client: client.credits.grant({"customer_external_id": "cust_1", "amount": 10, "metadata": {}}),
    ),
    (
        "credits.deduct",
        "/api/v1/credits/deduct",
        lambda client: client.credits.deduct({"customer_external_id": "cust_1", "amount": 10, "metadata": {}}),
    ),
]


class TestStaleAfterAWrite:
    @pytest.mark.parametrize(("name", "path", "write"), WRITES, ids=[name for name, _, _ in WRITES])
    def test_a_write_for_the_customer_makes_only_their_answers_stale(
        self, api: FakeApi, name: str, path: str, write: Callable[[MeterFlow], Any]
    ) -> None:
        seen = answer(api, CHECK, ALLOWED)
        other = answer(api, "/api/v1/entitlements/cust_2/check", ALLOWED)
        api.reply("POST", path, 201, {})
        client = make(api)
        client.entitlements.check("cust_1", "images.generated")
        client.entitlements.check("cust_2", "images.generated")
        write(client)
        client.entitlements.check("cust_1", "images.generated")
        client.entitlements.check("cust_2", "images.generated")
        assert (len(seen), len(other)) == (2, 1)

    def test_a_write_on_a_client_without_the_cache_just_writes(self, api: FakeApi) -> None:
        api.reply("POST", "/api/v1/usage/events", 201, {"id": "evt-1"})
        recorded = make(api, entitlements_cache=False).usage.record({"event_name": "x", "customer_external_id": "cust_1"})
        assert recorded["id"] == "evt-1"

    def test_a_failed_write_leaves_them_fresh(self, api: FakeApi) -> None:
        seen = answer(api, CHECK, ALLOWED)
        api.on("POST", "/api/v1/usage/events", lambda _request: api_error(422, "bad"))
        client = make(api)
        client.entitlements.check("cust_1", "images.generated")
        with pytest.raises(Exception):  # noqa: B017 — any refusal; only the cache's state matters here
            client.usage.record({"event_name": "x", "customer_external_id": "cust_1"})
        client.entitlements.check("cust_1", "images.generated")
        assert len(seen) == 1

    async def test_async_writes_make_them_stale_too(self, api: FakeApi) -> None:
        seen = answer(api, CHECK, ALLOWED)
        for _, path, _ in WRITES:
            api.reply("POST", path, 201, {})
        client = make_async(api)
        await client.entitlements.check("cust_1", "images.generated")
        await client.usage.record({"event_name": "x", "customer_external_id": "cust_1"})
        await client.entitlements.check("cust_1", "images.generated")
        await client.usage.record_batch([{"event_name": "x", "customer_external_id": "cust_1"}])
        await client.entitlements.check("cust_1", "images.generated")
        await client.credits.grant({"customer_external_id": "cust_1", "amount": 10, "metadata": {}})
        await client.entitlements.check("cust_1", "images.generated")
        await client.credits.deduct({"customer_external_id": "cust_1", "amount": 10, "metadata": {}})
        await client.entitlements.check("cust_1", "images.generated")
        assert len(seen) == 5


# ── Fallbacks ─────────────────────────────────────────────────────────────────


OUTAGES: list[tuple[int | None, type[Exception]]] = [(None, httpx.ConnectError), (503, ServerError), (429, RateLimitError)]


class TestStaleFallback:
    @pytest.mark.parametrize(("status", "error_class"), OUTAGES, ids=["network", "503", "429"])
    def test_the_last_answer_comes_back_marked_stale_and_on_error_is_told(
        self, api: FakeApi, clock: Clock, status: int | None, error_class: type[Exception]
    ) -> None:
        told: list[tuple[Exception, EntitlementFallbackContext]] = []
        answer(api, CHECK, ALLOWED)
        client = make(api, on_error=lambda error, context: told.append((error, context)))
        client.entitlements.check("cust_1", "images.generated")
        clock.now += 60
        fail(api, CHECK, status)

        assert client.entitlements.check("cust_1", "images.generated") == {**ALLOWED, "stale": True}
        [(error, context)] = told
        assert isinstance(error, error_class)
        assert context == EntitlementFallbackContext("cust_1", "images.generated", "stale")

    @pytest.mark.parametrize(("status", "error_class"), OUTAGES, ids=["network", "503", "429"])
    async def test_async_too(self, api: FakeApi, clock: Clock, status: int | None, error_class: type[Exception]) -> None:
        told: list[EntitlementFallbackContext] = []
        answer(api, CHECK, ALLOWED)
        client = make_async(api, on_error=lambda _error, context: told.append(context))
        await client.entitlements.check("cust_1", "images.generated")
        clock.now += 60
        fail(api, CHECK, status)
        assert await client.entitlements.check("cust_1", "images.generated") == {**ALLOWED, "stale": True}
        assert [context.fallback for context in told] == ["stale"]

    def test_an_answer_made_stale_by_a_write_is_still_a_fallback(self, api: FakeApi) -> None:
        answer(api, CHECK, ALLOWED)
        api.reply("POST", "/api/v1/usage/events", 201, {})
        client = make(api)
        client.entitlements.check("cust_1", "images.generated")
        client.usage.record({"event_name": "x", "customer_external_id": "cust_1"})
        fail(api, CHECK, 503)
        assert client.entitlements.check("cust_1", "images.generated").get("stale") is True

    def test_get_falls_back_to_its_last_answer_but_never_to_a_default(self, api: FakeApi) -> None:
        answer(api, LIST, LISTED, {})
        client = make(api, entitlement_defaults={"*": "allow"})
        fail(api, LIST, 503)
        with pytest.raises(ServerError):
            client.entitlements.get("cust_1")

        answer(api, LIST, LISTED)
        client.entitlements.get("cust_1")
        assert client.entitlement_cache is not None
        client.entitlement_cache.invalidate("cust_1")
        fail(api, LIST, 503)
        assert client.entitlements.get("cust_1") == {**LISTED, "stale": True}

    async def test_async_get_falls_back_to_its_last_answer(self, api: FakeApi) -> None:
        answer(api, LIST, LISTED)
        client = make_async(api)
        await client.entitlements.get("cust_1")
        assert client.entitlement_cache is not None
        client.entitlement_cache.invalidate("cust_1")
        fail(api, LIST, None)
        assert await client.entitlements.get("cust_1") == {**LISTED, "stale": True}


class TestDefaultFallback:
    def test_the_features_own_default_wins_over_the_wildcard(self, api: FakeApi) -> None:
        told: list[EntitlementFallbackContext] = []
        fail(api, CHECK, 503)
        client = make(
            api, entitlement_defaults={"images.generated": "allow", "*": "deny"}, on_error=lambda _error, context: told.append(context)
        )
        assert client.entitlements.check("cust_1", "images.generated") == {
            "feature": "images.generated",
            "feature_type": None,
            "allowed": True,
            "reason": "offline_default",
        }
        assert told == [EntitlementFallbackContext("cust_1", "images.generated", "default")]

    def test_the_wildcard_covers_a_feature_with_no_default(self, api: FakeApi) -> None:
        fail(api, "/api/v1/entitlements/cust_1/check", None)
        client = make(api, entitlement_defaults={"images.generated": "allow", "*": "deny"})
        result = client.entitlements.check("cust_1", "seats")
        assert (result["feature"], result["allowed"], result.get("reason")) == ("seats", False, "offline_default")

    def test_with_no_default_and_no_wildcard_it_raises_as_before(self, api: FakeApi) -> None:
        told: list[EntitlementFallbackContext] = []
        fail(api, CHECK, 503)
        client = make(api, entitlement_defaults={"seats": "allow"}, on_error=lambda _error, context: told.append(context))
        with pytest.raises(ServerError):
            client.entitlements.check("cust_1", "images.generated")
        assert told == []

    async def test_async_answers_the_default(self, api: FakeApi) -> None:
        fail(api, CHECK, 429)
        client = make_async(api, entitlement_defaults={"*": "allow"})
        assert (await client.entitlements.check("cust_1", "images.generated"))["allowed"] is True

    def test_what_on_error_raises_is_ignored(self, api: FakeApi) -> None:
        def broken(_error: Exception, _context: EntitlementFallbackContext) -> None:
            raise RuntimeError("the hook broke")

        fail(api, CHECK, 503)
        client = make(api, entitlement_defaults={"*": "allow"}, on_error=broken)
        assert client.entitlements.check("cust_1", "images.generated")["allowed"] is True

    def test_it_falls_back_only_once_the_retries_are_spent(self, api: FakeApi, no_sleep: list[float]) -> None:
        fail(api, CHECK, 503)
        client = MeterFlow("mf_test_abc", retries=1, transport=httpx.MockTransport(api.handle), entitlement_defaults={"*": "allow"})
        assert client.entitlements.check("cust_1", "images.generated").get("reason") == "offline_default"
        assert len(api.requests) == 2
        assert len(no_sleep) == 1


class TestAnAnswerIsNeverReplaced:
    @pytest.mark.parametrize(("status", "error_class"), [(401, AuthError), (403, AuthError), (404, NotFoundError)])
    def test_a_4xx_is_raised_even_with_a_cached_answer_and_a_default(self, api: FakeApi, status: int, error_class: type[Exception]) -> None:
        told: list[EntitlementFallbackContext] = []
        answer(api, CHECK, ALLOWED)
        client = make(api, entitlement_defaults={"*": "allow"}, on_error=lambda _error, context: told.append(context))
        client.entitlements.check("cust_1", "images.generated")
        assert client.entitlement_cache is not None
        client.entitlement_cache.invalidate("cust_1")
        fail(api, CHECK, status)
        with pytest.raises(error_class):
            client.entitlements.check("cust_1", "images.generated")
        assert told == []

    async def test_async_raises_a_403(self, api: FakeApi) -> None:
        fail(api, CHECK, 403)
        client = make_async(api, entitlement_defaults={"*": "allow"})
        with pytest.raises(AuthError):
            await client.entitlements.check("cust_1", "images.generated")
