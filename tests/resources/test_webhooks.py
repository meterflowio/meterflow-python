from __future__ import annotations

from typing import Any

import pytest

from meterflow import AsyncMeterFlow, MeterFlow, NotFoundError
from tests.conftest import FakeApi, api_error

WEBHOOK: dict[str, Any] = {
    "id": "wh-1",
    "project_id": "p",
    "url": "https://hooks.example/meterflow",
    "events": ["usage.recorded"],
    "low_balance_threshold": None,
    "is_active": True,
    "last_triggered_at": None,
    "failure_count": 0,
    "metadata_": {},
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}

DELIVERY: dict[str, Any] = {
    "id": "del-1",
    "webhook_id": "wh-1",
    "event_type": "usage.recorded",
    "payload": {"event": "usage.recorded", "environment": "test", "customer_id": "c"},
    "status": "success",
    "response_code": 200,
    "response_body": "ok",
    "attempts": 1,
    "created_at": "2026-01-01T00:00:00Z",
    "completed_at": "2026-01-01T00:00:01Z",
}


class TestList:
    def test_lists_the_projects_endpoints(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/webhooks", body=[WEBHOOK])
        result = client.webhooks.list()
        assert result[0]["url"] == "https://hooks.example/meterflow"

    def test_sends_no_project_id(self, api: FakeApi, client: MeterFlow) -> None:
        """The key's own project is the scope, and a query could not widen it."""
        api.reply("GET", "/api/v1/webhooks", body=[WEBHOOK])
        client.webhooks.list()
        assert api.last.url.query == b""

    def test_never_carries_a_secret(self, api: FakeApi, client: MeterFlow) -> None:
        """The secret is shown once in the dashboard and is never read back — not even by its owner."""
        api.reply("GET", "/api/v1/webhooks", body=[WEBHOOK])
        assert "secret" not in client.webhooks.list()[0]

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("GET", "/api/v1/webhooks", body=[WEBHOOK])
        assert (await async_client.webhooks.list())[0]["id"] == "wh-1"


class TestDeliveries:
    def test_reads_the_receipts(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/webhooks/wh-1/deliveries", body=[DELIVERY])
        [receipt] = client.webhooks.deliveries("wh-1")
        assert receipt["event_type"] == "usage.recorded"
        assert receipt["response_code"] == 200
        assert receipt["attempts"] == 1

    def test_encodes_the_webhook_id_into_the_path(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/webhooks/wh%201%2F..%2F2/deliveries", body=[])
        client.webhooks.deliveries("wh 1/../2")
        assert b"wh%201%2F..%2F2" in api.last.url.raw_path

    def test_another_projects_webhook_raises_not_found(self, api: FakeApi, client: MeterFlow) -> None:
        """404 rather than 403 on purpose: an opaque id must not confirm it exists elsewhere."""
        api.on("GET", "/api/v1/webhooks/someone-elses/deliveries", lambda _r: api_error(404, "Webhook not found"))
        with pytest.raises(NotFoundError):
            client.webhooks.deliveries("someone-elses")

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("GET", "/api/v1/webhooks/wh-1/deliveries", body=[DELIVERY])
        assert (await async_client.webhooks.deliveries("wh-1"))[0]["status"] == "success"


class TestDeliveryPage:
    def test_returns_a_page_and_passes_limit_and_cursor(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/webhooks/wh-1/deliveries/page", body={"data": [DELIVERY], "next_cursor": "Y3Vyc29y"})
        page = client.webhooks.delivery_page("wh-1", limit=25, cursor="abc")
        assert page["data"][0]["event_type"] == DELIVERY["event_type"]
        assert page["next_cursor"] == "Y3Vyc29y"
        assert dict(api.last.url.params) == {"limit": "25", "cursor": "abc"}

    def test_the_first_page_sends_no_query_string(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/webhooks/wh-1/deliveries/page", body={"data": [], "next_cursor": None})
        client.webhooks.delivery_page("wh-1")
        assert api.last.url.query == b""

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("GET", "/api/v1/webhooks/wh-1/deliveries/page", body={"data": [DELIVERY], "next_cursor": None})
        assert (await async_client.webhooks.delivery_page("wh-1", cursor="abc"))["next_cursor"] is None
        assert api.last.url.params["cursor"] == "abc"
