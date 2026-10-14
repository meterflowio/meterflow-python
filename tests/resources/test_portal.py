from __future__ import annotations

import json
from typing import Any

from meterflow import AsyncMeterFlow, MeterFlow
from tests.conftest import FakeApi

LINK: dict[str, Any] = {
    "url": "https://portal.meter-flow.test/?token=tok",
    "token": "tok",
    "expires_at": "2026-10-14T13:00:00Z",
    "customer_external_id": "customer_123",
    "environment": "live",
    "return_url": None,
    "topup_url": "https://acme.test/buy",
}


class TestCreateSession:
    def test_returns_the_link_to_send(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("POST", "/api/v1/portal/sessions", status=201, body=LINK)

        link = client.portal.create_session({"customer_external_id": "customer_123"})

        assert link["url"].endswith("token=tok")
        assert link["customer_external_id"] == "customer_123"
        assert link["topup_url"] == "https://acme.test/buy", "the page's 'buy more' is the tenant's own checkout"

    def test_sends_the_customer_the_links_and_the_lifetime(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("POST", "/api/v1/portal/sessions", status=201, body=LINK)

        client.portal.create_session(
            {"customer_external_id": "customer_123", "topup_url": "https://acme.test/buy", "expires_in_minutes": 15}
        )

        assert json.loads(api.last.content) == {
            "customer_external_id": "customer_123",
            "topup_url": "https://acme.test/buy",
            "expires_in_minutes": 15,
        }

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("POST", "/api/v1/portal/sessions", status=201, body=LINK)

        link = await async_client.portal.create_session({"customer_external_id": "customer_123"})

        assert link["token"] == "tok"
