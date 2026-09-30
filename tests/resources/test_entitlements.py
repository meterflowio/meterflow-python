from __future__ import annotations

from typing import Any

import pytest

from meterflow import AsyncMeterFlow, MeterFlow, NotFoundError
from tests.conftest import FakeApi, api_error

ALLOWED: dict[str, Any] = {
    "feature": "images.generated",
    "feature_type": "metered",
    "allowed": True,
    "reason": None,
    "limit_type": "hard",
    "included": 500,
    "used": "120",
    "remaining": "380",
    "period_start": "2026-09-01T00:00:00Z",
    "period_end": "2026-10-01T00:00:00Z",
}
ALL: dict[str, Any] = {
    "customer_id": "cust_1",
    "environment": "test",
    "subscription_id": "sub-1",
    "plan_id": "plan-1",
    "period_end": "2026-10-01T00:00:00Z",
    "entitlements": [ALLOWED, {"feature": "sso", "feature_type": "boolean", "allowed": True, "reason": None}],
}


class TestGet:
    def test_returns_the_plans_features_with_usage(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/entitlements/cust_1", body=ALL)
        result = client.entitlements.get("cust_1")
        assert len(result["entitlements"]) == 2
        assert result["entitlements"][1]["feature"] == "sso"
        assert api.last.url.query == b""

    def test_url_encodes_the_customer_id(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/entitlements/user%2F42", body={**ALL, "customer_id": "user/42", "entitlements": []})
        assert client.entitlements.get("user/42")["entitlements"] == []

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("GET", "/api/v1/entitlements/cust_1", body=ALL)
        assert (await async_client.entitlements.get("cust_1"))["plan_id"] == "plan-1"


class TestCheck:
    def test_sends_feature_and_no_quantity_by_default(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/entitlements/cust_1/check", body=ALLOWED)
        result = client.entitlements.check("cust_1", "images.generated")
        assert dict(api.last.url.params) == {"feature": "images.generated"}
        assert result["allowed"] is True
        assert result["remaining"] == "380"

    def test_passes_quantity_may_they_do_5_more(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/entitlements/cust_1/check", body=ALLOWED)
        client.entitlements.check("cust_1", "images.generated", quantity=5)
        assert dict(api.last.url.params) == {"feature": "images.generated", "quantity": "5"}

    def test_allowed_false_is_a_normal_answer_not_an_error(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply(
            "GET",
            "/api/v1/entitlements/cust_1/check",
            body={**ALLOWED, "allowed": False, "used": "500", "remaining": "0", "reason": "hard_limit_reached"},
        )
        result = client.entitlements.check("cust_1", "images.generated")
        assert result["allowed"] is False
        assert result["reason"] == "hard_limit_reached"

    def test_unknown_feature_key_is_not_found_a_typo_not_a_plan(self, api: FakeApi, client: MeterFlow) -> None:
        api.on("GET", "/api/v1/entitlements/cust_1/check", lambda _r: api_error(404, "Unknown feature 'imagess.generated'"))
        with pytest.raises(NotFoundError, match="Unknown feature"):
            client.entitlements.check("cust_1", "imagess.generated")

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("GET", "/api/v1/entitlements/cust_1/check", body=ALLOWED)
        result = await async_client.entitlements.check("cust_1", "images.generated", quantity=2)
        assert result["allowed"] is True
        assert dict(api.last.url.params)["quantity"] == "2"
