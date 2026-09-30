from __future__ import annotations

from typing import Any

import pytest

from meterflow import MAX_BATCH_EVENTS, AsyncMeterFlow, MeterFlow, PayloadTooLargeError
from meterflow.types import UsageEventRequest
from tests.conftest import FakeApi

EVENT: dict[str, Any] = {
    "id": "evt-1",
    "project_id": "p",
    "customer_external_id": "cust-1",
    "event_name": "api_call",
    "value": "1",
    "properties": {},
    "idempotency_key": None,
    "timestamp": "2026-01-01T00:00:00Z",
    "processed": False,
    "created_at": "2026-01-01T00:00:00Z",
}
SUMMARY: dict[str, Any] = {
    "project_id": "p",
    "customer_external_id": "cust-1",
    "from_": "2026-01-01T00:00:00Z",
    "to": "2026-01-31T23:59:59Z",
    "meters": [{"meter_id": "m-1", "meter_name": "api_call", "event_name": "api_call", "aggregation_type": "count", "value": "42"}],
}
ONE: UsageEventRequest = {"event_name": "api_call", "customer_external_id": "c", "value": 1, "properties": {}}


class TestRecord:
    def test_posts_the_event(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("POST", "/api/v1/usage/events", 201, EVENT)
        result = client.usage.record(ONE, idempotency_key="idem-key")
        assert result["id"] == "evt-1"
        assert api.last_json()["event_name"] == "api_call"
        assert api.last.headers["idempotency-key"] == "idem-key"

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("POST", "/api/v1/usage/events", 201, EVENT)
        assert (await async_client.usage.record(ONE))["processed"] is False


class TestRecordBatch:
    def test_wraps_events_in_an_envelope(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("POST", "/api/v1/usage/events/batch", 201, [EVENT])
        result = client.usage.record_batch([ONE], idempotency_key="batch-key")
        assert api.last_json() == {"events": [ONE]}
        assert api.last.headers["idempotency-key"] == "batch-key"
        assert len(result) == 1

    def test_sends_exactly_the_cap(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("POST", "/api/v1/usage/events/batch", 201, [EVENT])
        client.usage.record_batch([ONE] * MAX_BATCH_EVENTS)
        assert len(api.last_json()["events"]) == MAX_BATCH_EVENTS

    def test_one_more_is_refused_locally_and_never_sent(self, api: FakeApi, client: MeterFlow) -> None:
        with pytest.raises(PayloadTooLargeError) as excinfo:
            client.usage.record_batch([ONE] * (MAX_BATCH_EVENTS + 1))
        assert str(MAX_BATCH_EVENTS) in excinfo.value.message
        assert str(MAX_BATCH_EVENTS + 1) in excinfo.value.message
        assert excinfo.value.retryable is False
        assert api.requests == []

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("POST", "/api/v1/usage/events/batch", 201, [EVENT])
        assert len(await async_client.usage.record_batch([ONE], idempotency_key="b")) == 1
        assert api.last.headers["idempotency-key"] == "b"

    async def test_async_refuses_locally_too(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        with pytest.raises(PayloadTooLargeError):
            await async_client.usage.record_batch([ONE] * (MAX_BATCH_EVENTS + 1))
        assert api.requests == []


class TestSummary:
    def test_gets_the_summary(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/usage/cust-1", body=SUMMARY)
        result = client.usage.summary("cust-1")
        assert result["customer_external_id"] == "cust-1"
        assert len(result["meters"]) == 1
        assert api.last.url.query == b""

    def test_passes_meter_id_from_and_to(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/usage/cust-1", body=SUMMARY)
        client.usage.summary("cust-1", meter_id="m-1", from_="2026-01-01", to="2026-01-31")
        assert dict(api.last.url.params) == {"meter_id": "m-1", "from_": "2026-01-01", "to": "2026-01-31"}

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("GET", "/api/v1/usage/cust-1", body=SUMMARY)
        await async_client.usage.summary("cust-1", to="2026-01-31")
        assert dict(api.last.url.params) == {"to": "2026-01-31"}
