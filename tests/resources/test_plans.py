from __future__ import annotations

from typing import Any

import pytest

from meterflow import AsyncMeterFlow, MeterFlow, NotFoundError
from tests.conftest import FakeApi, api_error

PLAN: dict[str, Any] = {
    "id": "plan-1",
    "project_id": "p",
    "name": "Pro",
    "slug": "pro",
    "description": None,
    "price": "29.00",
    "currency": "USD",
    "billing_period": "monthly",
    "trial_days": 0,
    "is_public": True,
    "is_active": True,
    "metadata_": {},
    "meter_limits": [],
    "features": ["sso"],
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}


class TestList:
    def test_lists(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/plans", body=[PLAN])
        result = client.plans.list()
        assert result[0]["features"] == ["sso"]
        assert api.last.url.query == b""

    def test_passes_project_id(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/plans", body=[PLAN])
        client.plans.list(project_id="p")
        assert dict(api.last.url.params) == {"project_id": "p"}

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("GET", "/api/v1/plans", body=[PLAN])
        assert (await async_client.plans.list())[0]["slug"] == "pro"


class TestGet:
    def test_gets(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/plans/plan-1", body=PLAN)
        assert client.plans.get("plan-1")["price"] == "29.00"

    def test_passes_project_id(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/plans/plan-1", body=PLAN)
        client.plans.get("plan-1", project_id="p")
        assert dict(api.last.url.params) == {"project_id": "p"}

    def test_404_raises_not_found(self, api: FakeApi, client: MeterFlow) -> None:
        api.on("GET", "/api/v1/plans/nope", lambda _r: api_error(404, "Plan not found"))
        with pytest.raises(NotFoundError):
            client.plans.get("nope")

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("GET", "/api/v1/plans/plan-1", body=PLAN)
        assert (await async_client.plans.get("plan-1"))["name"] == "Pro"
