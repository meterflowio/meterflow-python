from __future__ import annotations

import httpx
import pytest

from meterflow import (
    AsyncMeterFlow,
    AuthError,
    ConflictError,
    InsufficientCreditsError,
    MeterFlow,
    MeterFlowError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from tests.conftest import GRANT_BODY, FakeApi, api_error

GRANT = ("POST", "/api/v1/credits/grant")


def test_reads_error_message_the_shape_the_api_really_sends(api: FakeApi, client: MeterFlow) -> None:
    api.on(*GRANT, lambda _r: api_error(401, "Invalid API key"))
    with pytest.raises(AuthError) as excinfo:
        client.credits.grant(GRANT_BODY)
    assert excinfo.value.message == "Invalid API key"
    assert str(excinfo.value) == "Invalid API key"


def test_422_field_detail_in_message_and_fields(api: FakeApi, client: MeterFlow) -> None:
    fields = [{"field": "amount", "message": "must be greater than 0"}, {"field": "customer_external_id", "message": "must not be empty"}]
    api.on(*GRANT, lambda _r: api_error(422, "Validation failed", fields=fields))
    with pytest.raises(ValidationError) as excinfo:
        client.credits.grant(GRANT_BODY)
    assert excinfo.value.message == "Validation failed: amount: must be greater than 0; customer_external_id: must not be empty"
    assert excinfo.value.fields == fields


def test_422_without_fields_yields_an_empty_list(api: FakeApi, client: MeterFlow) -> None:
    api.on(*GRANT, lambda _r: api_error(422, "Validation failed"))
    with pytest.raises(ValidationError) as excinfo:
        client.credits.grant(GRANT_BODY)
    assert excinfo.value.fields == []


def test_422_ignores_malformed_field_entries(api: FakeApi, client: MeterFlow) -> None:
    api.on(*GRANT, lambda _r: api_error(422, "Validation failed", fields=[{"field": "amount"}, "junk", {"field": "x", "message": "bad"}]))
    with pytest.raises(ValidationError) as excinfo:
        client.credits.grant(GRANT_BODY)
    assert excinfo.value.fields == [{"field": "x", "message": "bad"}]


@pytest.mark.parametrize(
    ("status", "error_class", "error_type", "retryable"),
    [
        (401, AuthError, "auth_error", False),
        (403, AuthError, "auth_error", False),
        (402, InsufficientCreditsError, "insufficient_credits", False),
        (404, NotFoundError, "not_found", False),
        (409, ConflictError, "conflict", False),
        (413, PayloadTooLargeError, "payload_too_large", False),
        (422, ValidationError, "validation_error", False),
        (429, RateLimitError, "rate_limit", True),
        (500, ServerError, "server_error", True),
        (503, ServerError, "server_error", True),
    ],
)
def test_status_to_error_mapping(
    api: FakeApi, client: MeterFlow, status: int, error_class: type[MeterFlowError], error_type: str, retryable: bool
) -> None:
    api.on(
        *GRANT, lambda _r: httpx.Response(status, json={"error": {"code": status, "message": "boom"}}, headers={"x-request-id": "req-1"})
    )
    with pytest.raises(error_class) as excinfo:
        client.credits.grant(GRANT_BODY)
    error = excinfo.value
    assert error.status_code == status
    assert error.error_type == error_type
    assert error.retryable is retryable
    assert error.request_id == "req-1"
    assert isinstance(error, MeterFlowError)


def test_accepts_fastapi_default_detail_as_fallback(api: FakeApi, client: MeterFlow) -> None:
    api.on(*GRANT, lambda _r: httpx.Response(401, json={"detail": "specific error"}))
    with pytest.raises(AuthError, match="specific error"):
        client.credits.grant(GRANT_BODY)


def test_falls_back_to_json_dump_for_an_unrecognised_body(api: FakeApi, client: MeterFlow) -> None:
    api.on(*GRANT, lambda _r: httpx.Response(401, json={"detail": [{"msg": "field required", "loc": ["body"]}]}))
    with pytest.raises(AuthError, match="field required"):
        client.credits.grant(GRANT_BODY)


def test_falls_back_to_json_dump_for_a_non_object_body(api: FakeApi, client: MeterFlow) -> None:
    api.on(*GRANT, lambda _r: httpx.Response(401, json=["nope"]))
    with pytest.raises(AuthError, match='\\["nope"\\]'):
        client.credits.grant(GRANT_BODY)


def test_falls_back_to_reason_phrase_when_body_is_not_json(api: FakeApi, client: MeterFlow) -> None:
    api.on(*GRANT, lambda _r: httpx.Response(400, content=b"Bad Request", headers={"content-type": "text/plain"}))
    with pytest.raises(MeterFlowError) as excinfo:
        client.credits.grant(GRANT_BODY)
    assert excinfo.value.message
    assert excinfo.value.status_code == 400


def test_unmapped_4xx_is_a_generic_non_retryable_error(api: FakeApi, client: MeterFlow) -> None:
    api.on(*GRANT, lambda _r: api_error(418, "teapot"))
    with pytest.raises(MeterFlowError) as excinfo:
        client.credits.grant(GRANT_BODY)
    assert type(excinfo.value) is MeterFlowError
    assert excinfo.value.status_code == 418
    assert excinfo.value.error_type == "request_error"
    assert excinfo.value.retryable is False


def test_rate_limit_exposes_retry_after_and_tolerates_a_missing_or_bad_header(api: FakeApi, client: MeterFlow) -> None:
    api.on(*GRANT, lambda _r: httpx.Response(429, json={"error": {"code": 429, "message": "slow down"}}, headers={"Retry-After": "60"}))
    with pytest.raises(RateLimitError) as excinfo:
        client.credits.grant(GRANT_BODY)
    assert excinfo.value.retry_after == 60

    api.on(
        *GRANT,
        lambda _r: httpx.Response(429, json={"error": {"code": 429, "message": "slow down"}}, headers={"Retry-After": "Wed, 21 Oct"}),
    )
    with pytest.raises(RateLimitError) as excinfo:
        client.credits.grant(GRANT_BODY)
    assert excinfo.value.retry_after is None


async def test_async_client_maps_errors_the_same_way(api: FakeApi, async_client: AsyncMeterFlow) -> None:
    api.on(*GRANT, lambda _r: api_error(402, "Insufficient credits"))
    with pytest.raises(InsufficientCreditsError) as excinfo:
        await async_client.credits.grant(GRANT_BODY)
    assert excinfo.value.message == "Insufficient credits"
    assert excinfo.value.status_code == 402
