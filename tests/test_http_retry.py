from __future__ import annotations

import httpx
import pytest

from meterflow import AsyncMeterFlow, AuthError, MeterFlow, RateLimitError, ServerError, ValidationError
from meterflow._retry import RetryPolicy
from tests.conftest import GRANT_BODY, TX, FakeApi, api_error

GRANT = ("POST", "/api/v1/credits/grant")


def make_client(api: FakeApi, retries: int) -> MeterFlow:
    return MeterFlow("mf_test_abc", retries=retries, transport=httpx.MockTransport(api.handle))


def make_async_client(api: FakeApi, retries: int) -> AsyncMeterFlow:
    return AsyncMeterFlow("mf_test_abc", retries=retries, transport=httpx.MockTransport(api.handle_async))


def flaky(api: FakeApi, failures: list[httpx.Response]) -> None:
    """Answer with each queued failure in turn, then succeed."""

    def handler(_request: httpx.Request) -> httpx.Response:
        if failures:
            return failures.pop(0)
        return httpx.Response(201, json=TX)

    api.on(*GRANT, handler)


class TestRetryOn5xx:
    def test_succeeds_on_second_attempt_after_503(self, api: FakeApi, no_sleep: list[float]) -> None:
        flaky(api, [api_error(503, "down")])
        result = make_client(api, retries=1).credits.grant(GRANT_BODY)
        assert result["id"] == "tx-1"
        assert len(api.requests) == 2
        assert len(no_sleep) == 1
        assert 0.75 <= no_sleep[0] <= 1.25  # 1 s × 2^0, ±25 % jitter

    def test_raises_server_error_after_exhausting_retries(self, api: FakeApi) -> None:
        api.on(*GRANT, lambda _r: api_error(500, "down"))
        with pytest.raises(ServerError):
            make_client(api, retries=1).credits.grant(GRANT_BODY)
        assert len(api.requests) == 2

    def test_backoff_grows_exponentially_and_is_capped(self, api: FakeApi, no_sleep: list[float]) -> None:
        api.on(*GRANT, lambda _r: api_error(500, "down"))
        with pytest.raises(ServerError):
            make_client(api, retries=5).credits.grant(GRANT_BODY)
        assert len(api.requests) == 6
        bases = [1, 2, 4, 8, 10]  # 16 would exceed the 10 s cap
        for delay, base in zip(no_sleep, bases, strict=True):
            assert base * 0.75 <= delay <= base * 1.25


class TestNoRetryOn4xx:
    def test_does_not_retry_422(self, api: FakeApi, no_sleep: list[float]) -> None:
        api.on(*GRANT, lambda _r: api_error(422, "bad input"))
        with pytest.raises(ValidationError):
            make_client(api, retries=3).credits.grant(GRANT_BODY)
        assert len(api.requests) == 1
        assert no_sleep == []

    def test_does_not_retry_401(self, api: FakeApi) -> None:
        api.on(*GRANT, lambda _r: api_error(401, "unauthorized"))
        with pytest.raises(AuthError):
            make_client(api, retries=3).credits.grant(GRANT_BODY)
        assert len(api.requests) == 1


class TestRateLimit:
    def test_429_waits_for_retry_after_verbatim_then_retries(self, api: FakeApi, no_sleep: list[float]) -> None:
        flaky(api, [httpx.Response(429, json={"error": {"code": 429, "message": "rate limited"}}, headers={"Retry-After": "7"})])
        result = make_client(api, retries=3).credits.grant(GRANT_BODY)
        assert result["id"] == "tx-1"
        assert len(api.requests) == 2
        assert no_sleep == [7.0]

    def test_429_without_retry_after_uses_backoff(self, api: FakeApi, no_sleep: list[float]) -> None:
        flaky(api, [api_error(429, "rate limited")])
        make_client(api, retries=3).credits.grant(GRANT_BODY)
        assert 0.75 <= no_sleep[0] <= 1.25

    def test_exposes_retry_after_when_retries_are_disabled(self, api: FakeApi) -> None:
        api.on(
            *GRANT, lambda _r: httpx.Response(429, json={"error": {"code": 429, "message": "rate limited"}}, headers={"Retry-After": "60"})
        )
        with pytest.raises(RateLimitError) as excinfo:
            make_client(api, retries=0).credits.grant(GRANT_BODY)
        assert excinfo.value.retry_after == 60


class TestNetworkErrors:
    def test_retries_a_connection_error_and_recovers(self, api: FakeApi) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ConnectError("connection refused", request=request)
            return httpx.Response(201, json=TX)

        api.on(*GRANT, handler)
        result = make_client(api, retries=3).credits.grant(GRANT_BODY)
        assert result["id"] == "tx-1"
        assert calls == 2

    def test_reraises_the_transport_error_once_retries_are_exhausted(self, api: FakeApi) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        api.on(*GRANT, handler)
        with pytest.raises(httpx.ReadTimeout):
            make_client(api, retries=1).credits.grant(GRANT_BODY)


class TestAsyncRetry:
    async def test_async_client_retries_5xx_then_succeeds(self, api: FakeApi, no_sleep: list[float]) -> None:
        flaky(api, [api_error(503, "down")])
        result = await make_async_client(api, retries=1).credits.grant(GRANT_BODY)
        assert result["id"] == "tx-1"
        assert len(api.requests) == 2
        assert len(no_sleep) == 1

    async def test_async_client_honours_retry_after(self, api: FakeApi, no_sleep: list[float]) -> None:
        flaky(api, [httpx.Response(429, json={"error": {"code": 429, "message": "rate limited"}}, headers={"Retry-After": "3"})])
        await make_async_client(api, retries=2).credits.grant(GRANT_BODY)
        assert no_sleep == [3.0]

    async def test_async_client_does_not_retry_4xx(self, api: FakeApi) -> None:
        api.on(*GRANT, lambda _r: api_error(401, "unauthorized"))
        with pytest.raises(AuthError):
            await make_async_client(api, retries=3).credits.grant(GRANT_BODY)
        assert len(api.requests) == 1


class TestRetryPolicy:
    def test_gives_up_on_the_last_attempt(self) -> None:
        assert RetryPolicy(retries=2).delay_before_retry(2, ServerError("x")) is None

    def test_gives_up_on_non_retryable_errors(self) -> None:
        assert RetryPolicy(retries=3).delay_before_retry(0, AuthError("x")) is None

    def test_no_jitter_gives_exact_bases(self) -> None:
        policy = RetryPolicy(retries=5, jitter=False)
        assert [policy.delay_before_retry(attempt, ServerError("x")) for attempt in range(4)] == [1.0, 2.0, 4.0, 8.0]

    def test_unknown_exceptions_are_retried(self) -> None:
        assert RetryPolicy(retries=1, jitter=False).delay_before_retry(0, RuntimeError("socket closed")) == 1.0
