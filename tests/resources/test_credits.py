from __future__ import annotations

from typing import Any

import httpx
import pytest

from meterflow import AsyncMeterFlow, InsufficientCreditsError, MeterFlow, NotFoundError
from tests.conftest import BASE, TX, FakeApi, api_error

BALANCE: dict[str, Any] = {
    "id": "bal-1",
    "project_id": "p",
    "customer_external_id": "cust-1",
    "balance": "100",
    "total_granted": "100",
    "total_consumed": "0",
    "version": 1,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}


class TestGrant:
    def test_posts_body_and_returns_the_transaction(self, api: FakeApi, client: MeterFlow) -> None:
        api.on("POST", "/api/v1/credits/grant", lambda _r: httpx.Response(201, json=TX, headers={"x-request-id": "req-abc"}))
        result = client.credits.grant({"amount": 100, "customer_external_id": "cust-1", "metadata": {}})
        assert result["id"] == "tx-1"
        assert api.last_json()["amount"] == 100
        assert str(api.last.url) == f"{BASE}/credits/grant"

    def test_forwards_the_idempotency_key(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("POST", "/api/v1/credits/grant", 201, TX)
        client.credits.grant({"amount": 1, "customer_external_id": "c", "metadata": {}}, idempotency_key="grant-1")
        assert api.last.headers["idempotency-key"] == "grant-1"

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("POST", "/api/v1/credits/grant", 201, TX)
        result = await async_client.credits.grant({"amount": 1, "customer_external_id": "c", "metadata": {}}, idempotency_key="k")
        assert result["id"] == "tx-1"
        assert api.last.headers["idempotency-key"] == "k"


class TestDeduct:
    def test_posts_and_returns_the_transaction(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("POST", "/api/v1/credits/deduct", 201, {**TX, "transaction_type": "deduct"})
        result = client.credits.deduct({"amount": 25, "customer_external_id": "cust-1", "metadata": {}}, idempotency_key="d-1")
        assert result["transaction_type"] == "deduct"
        assert api.last.headers["idempotency-key"] == "d-1"

    def test_402_raises_insufficient_credits(self, api: FakeApi, client: MeterFlow) -> None:
        api.on("POST", "/api/v1/credits/deduct", lambda _r: api_error(402, "Insufficient credits"))
        with pytest.raises(InsufficientCreditsError, match="Insufficient credits"):
            client.credits.deduct({"amount": 999, "customer_external_id": "c", "metadata": {}})

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("POST", "/api/v1/credits/deduct", 201, {**TX, "transaction_type": "deduct"})
        result = await async_client.credits.deduct({"amount": 1, "customer_external_id": "c", "metadata": {}})
        assert result["transaction_type"] == "deduct"

    async def test_async_402(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.on("POST", "/api/v1/credits/deduct", lambda _r: api_error(402, "Insufficient credits"))
        with pytest.raises(InsufficientCreditsError):
            await async_client.credits.deduct({"amount": 999, "customer_external_id": "c", "metadata": {}})


class TestBalance:
    def test_gets_the_balance(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/credits/cust-1/balance", body=BALANCE)
        assert client.credits.balance("cust-1")["balance"] == "100"

    def test_url_encodes_the_customer_id(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/credits/user%2F42%40x.io/balance", body=BALANCE)
        client.credits.balance("user/42@x.io")
        assert api.last.url.raw_path == b"/api/v1/credits/user%2F42%40x.io/balance"

    def test_404_raises_not_found(self, api: FakeApi, client: MeterFlow) -> None:
        api.on("GET", "/api/v1/credits/nobody/balance", lambda _r: api_error(404, "No balance"))
        with pytest.raises(NotFoundError):
            client.credits.balance("nobody")

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("GET", "/api/v1/credits/cust-1/balance", body=BALANCE)
        assert (await async_client.credits.balance("cust-1"))["total_granted"] == "100"


class TestTransactions:
    def test_returns_a_page_rather_than_the_whole_history(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/credits/cust-1/transactions", body={"data": [TX, TX], "next_cursor": "Y3Vyc29y"})
        page = client.credits.transactions("cust-1")
        assert len(page["data"]) == 2
        assert page["next_cursor"] == "Y3Vyc29y"
        assert api.last.url.query == b"", "no page asked for, no query string"

    def test_the_last_page_says_there_is_nothing_after_it(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/credits/cust-1/transactions", body={"data": [], "next_cursor": None})
        page = client.credits.transactions("cust-1")
        assert page == {"data": [], "next_cursor": None}

    def test_limit_and_cursor_travel_as_query_parameters(self, api: FakeApi, client: MeterFlow) -> None:
        api.reply("GET", "/api/v1/credits/cust-1/transactions", body={"data": [TX], "next_cursor": None})
        client.credits.transactions("cust-1", limit=25, cursor="Y3Vyc29y")
        assert b"limit=25" in api.last.url.query
        assert b"cursor=Y3Vyc29y" in api.last.url.query

    async def test_async(self, api: FakeApi, async_client: AsyncMeterFlow) -> None:
        api.reply("GET", "/api/v1/credits/cust-1/transactions", body={"data": [TX], "next_cursor": None})
        assert (await async_client.credits.transactions("cust-1"))["data"][0]["id"] == "tx-1"
