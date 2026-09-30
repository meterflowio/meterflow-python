from __future__ import annotations

from typing import Any

import httpx
import pytest

from meterflow import AsyncMeterFlow, ConflictError, MeterFlow, NotFoundError
from tests.conftest import FakeApi, api_error

SUB: dict[str, Any] = {
    "id": "sub-1",
    "project_id": "p",
    "plan_id": "plan-1",
    "customer_external_id": "cust-1",
    "status": "active",
    "current_period_start": "2026-01-01T00:00:00Z",
    "current_period_end": "2026-02-01T00:00:00Z",
    "trial_ends_at": None,
    "canceled_at": None,
    "metadata_": {},
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}


class TestCreate:
    def test_posts_and_returns_the_subscription(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("POST", "/api/v1/subscriptions", 201, SUB)
        result = client.subscriptions.create(
            {"plan_id": "plan-1", "customer_external_id": "cust-1", "metadata": {}}, idempotency_key="sub-k"
        )
        assert result["status"] == "active"
        assert api.last_json()["plan_id"] == "plan-1"
        assert api.last.headers["idempotency-key"] == "sub-k"

    def test_409_raises_conflict(self, api: FakeApi, client: MeterFlow) -> None:
        api.on("POST", "/api/v1/subscriptions", lambda _r: api_error(409, "already subscribed"))
        with pytest.raises(ConflictError):
            client.subscriptions.create({"plan_id": "plan-1", "customer_external_id": "cust-1", "metadata": {}})

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("POST", "/api/v1/subscriptions", 201, SUB)
        assert (await async_client.subscriptions.create({"plan_id": "plan-1", "customer_external_id": "cust-1", "metadata": {}}))[
            "id"
        ] == "sub-1"


class TestList:
    def test_lists(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/subscriptions", body=[SUB])
        assert len(client.subscriptions.list()) == 1
        assert api.last.url.query == b""

    def test_passes_customer_id(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/subscriptions", body=[SUB])
        client.subscriptions.list(customer_id="cust-1")
        assert dict(api.last.url.params) == {"customer_id": "cust-1"}

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("GET", "/api/v1/subscriptions", body=[])
        assert await async_client.subscriptions.list(customer_id="x") == []


class TestGet:
    def test_gets(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/subscriptions/sub-1", body=SUB)
        assert client.subscriptions.get("sub-1")["id"] == "sub-1"

    def test_404_raises_not_found(self, api: FakeApi, client: MeterFlow) -> None:
        api.on("GET", "/api/v1/subscriptions/nope", lambda _r: api_error(404, "Subscription not found"))
        with pytest.raises(NotFoundError):
            client.subscriptions.get("nope")

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("GET", "/api/v1/subscriptions/sub-1", body=SUB)
        assert (await async_client.subscriptions.get("sub-1"))["plan_id"] == "plan-1"


class TestUpdate:
    def test_patches_and_returns(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("PATCH", "/api/v1/subscriptions/sub-1", body={**SUB, "status": "paused"})
        result = client.subscriptions.update("sub-1", {"status": "paused"}, idempotency_key="u-1")
        assert result["status"] == "paused"
        assert api.last.method == "PATCH"
        assert api.last_json() == {"status": "paused"}
        assert api.last.headers["idempotency-key"] == "u-1"

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("PATCH", "/api/v1/subscriptions/sub-1", body={**SUB, "status": "canceled"})
        assert (await async_client.subscriptions.update("sub-1", {"status": "canceled"}))["status"] == "canceled"


class TestDelete:
    def test_deletes_and_returns_none_on_204(self, api: FakeApi, client: MeterFlow) -> None:
        api.on("DELETE", "/api/v1/subscriptions/sub-1", lambda _r: httpx.Response(204))
        client.subscriptions.delete("sub-1")
        assert api.last.method == "DELETE"

    def test_an_empty_200_body_is_none_too(self, api: FakeApi, client: MeterFlow) -> None:
        api.on("DELETE", "/api/v1/subscriptions/sub-1", lambda _r: httpx.Response(200, content=b""))
        client.subscriptions.delete("sub-1")
        assert api.last.method == "DELETE"

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.on("DELETE", "/api/v1/subscriptions/sub-1", lambda _r: httpx.Response(204))
        await async_client.subscriptions.delete("sub-1")
        assert api.last.method == "DELETE"
