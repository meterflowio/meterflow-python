from __future__ import annotations

import httpx
import pytest

from meterflow import AsyncMeterFlow, MeterFlow, __version__
from tests.conftest import BASE, TX, FakeApi


class TestConstructor:
    def test_accepts_live_and_test_prefixes(self) -> None:
        MeterFlow("mf_live_abc")
        MeterFlow("mf_test_abc")
        AsyncMeterFlow("mf_live_abc")

    def test_rejects_other_prefixes(self) -> None:
        with pytest.raises(ValueError, match="mf_live_ or mf_test_"):
            MeterFlow("sk_live_abc")
        with pytest.raises(ValueError, match="mf_live_ or mf_test_"):
            AsyncMeterFlow("sk_live_abc")

    def test_defaults(self) -> None:
        options = MeterFlow("mf_test_x").options
        assert options.base_url == "https://api.meter-flow.com/api/v1/"
        assert options.timeout == 30.0
        assert options.retries == 3

    def test_custom_base_url_with_or_without_trailing_slash(self) -> None:
        assert MeterFlow("mf_test_x", base_url="http://localhost:8000/api/v1").options.base_url == "http://localhost:8000/api/v1/"
        assert MeterFlow("mf_test_x", base_url="http://localhost:8000/api/v1/").options.base_url == "http://localhost:8000/api/v1/"

    def test_exposes_the_five_resources(self) -> None:
        for client in (MeterFlow("mf_test_x"), AsyncMeterFlow("mf_test_x")):
            for name in ("credits", "usage", "subscriptions", "plans", "entitlements"):
                assert getattr(client, name) is not None


class TestTransport:
    def test_headers_on_every_request(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/plans", body=[])
        client.plans.list()
        headers = api.last.headers
        assert headers["authorization"] == "Bearer mf_test_abc"
        assert headers["user-agent"] == f"meterflow-python/{__version__}"
        assert headers["accept"] == "application/json"
        assert "content-type" not in headers  # no body → no content type
        assert "idempotency-key" not in headers

    def test_json_body_and_content_type_on_writes(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("POST", "/api/v1/credits/grant", 201, TX)
        client.credits.grant({"amount": 10, "customer_external_id": "c", "metadata": {}})
        assert api.last.headers["content-type"] == "application/json"
        assert api.last_json() == {"amount": 10, "customer_external_id": "c", "metadata": {}}
        assert str(api.last.url) == f"{BASE}/credits/grant"

    def test_none_query_values_are_not_sent(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/plans", body=[])
        client.plans.list()
        assert api.last.url.query == b""

    def test_context_manager_closes_the_connection_pool(self, api: FakeApi) -> None:
        with MeterFlow("mf_test_abc", retries=0, transport=httpx.MockTransport(api.handle)) as client:
            api.reply("GET", "/api/v1/plans", body=[])
            assert client.plans.list() == []
        assert client._http.is_closed

    async def test_async_context_manager_closes_the_connection_pool(self, api: FakeApi) -> None:
        async with AsyncMeterFlow("mf_test_abc", retries=0, transport=httpx.MockTransport(api.handle_async)) as client:
            api.reply("GET", "/api/v1/plans", body=[])
            assert await client.plans.list() == []
        assert client._http.is_closed

    async def test_async_client_sends_the_same_headers(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("GET", "/api/v1/plans", body=[])
        await async_client.plans.list()
        assert api.last.headers["authorization"] == "Bearer mf_test_abc"
        assert api.last.headers["user-agent"] == f"meterflow-python/{__version__}"
