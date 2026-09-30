"""Credits — an append-only ledger per customer: grant up, deduct down, never edited in place."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._http import RequestSpec, encode_path_segment
from ..types import CreditBalanceResponse, CreditDeductRequest, CreditGrantRequest, CreditTransactionResponse

if TYPE_CHECKING:
    from ..client import AsyncMeterFlow, MeterFlow


def grant_spec(body: CreditGrantRequest, idempotency_key: str | None) -> RequestSpec:
    return RequestSpec("POST", "credits/grant", body=body, idempotency_key=idempotency_key)


def deduct_spec(body: CreditDeductRequest, idempotency_key: str | None) -> RequestSpec:
    return RequestSpec("POST", "credits/deduct", body=body, idempotency_key=idempotency_key)


def balance_spec(customer_id: str) -> RequestSpec:
    return RequestSpec("GET", f"credits/{encode_path_segment(customer_id)}/balance")


def transactions_spec(customer_id: str) -> RequestSpec:
    return RequestSpec("GET", f"credits/{encode_path_segment(customer_id)}/transactions")


class CreditsResource:
    def __init__(self, client: MeterFlow) -> None:
        self._client = client

    def grant(self, body: CreditGrantRequest, *, idempotency_key: str | None = None) -> CreditTransactionResponse:
        """Add credits (plan renewals, top-ups, goodwill). Returns the ledger line."""
        result: CreditTransactionResponse = self._client.request(grant_spec(body, idempotency_key))
        return result

    def deduct(self, body: CreditDeductRequest, *, idempotency_key: str | None = None) -> CreditTransactionResponse:
        """Remove credits. Raises ``InsufficientCreditsError`` (402) rather than take the customer below zero."""
        result: CreditTransactionResponse = self._client.request(deduct_spec(body, idempotency_key))
        return result

    def balance(self, customer_id: str) -> CreditBalanceResponse:
        """The customer's current position — amounts are decimal strings."""
        result: CreditBalanceResponse = self._client.request(balance_spec(customer_id))
        return result

    def transactions(self, customer_id: str) -> list[CreditTransactionResponse]:
        """The full history, newest first."""
        result: list[CreditTransactionResponse] = self._client.request(transactions_spec(customer_id))
        return result


class AsyncCreditsResource:
    def __init__(self, client: AsyncMeterFlow) -> None:
        self._client = client

    async def grant(self, body: CreditGrantRequest, *, idempotency_key: str | None = None) -> CreditTransactionResponse:
        """Add credits (plan renewals, top-ups, goodwill). Returns the ledger line."""
        result: CreditTransactionResponse = await self._client.request(grant_spec(body, idempotency_key))
        return result

    async def deduct(self, body: CreditDeductRequest, *, idempotency_key: str | None = None) -> CreditTransactionResponse:
        """Remove credits. Raises ``InsufficientCreditsError`` (402) rather than take the customer below zero."""
        result: CreditTransactionResponse = await self._client.request(deduct_spec(body, idempotency_key))
        return result

    async def balance(self, customer_id: str) -> CreditBalanceResponse:
        """The customer's current position — amounts are decimal strings."""
        result: CreditBalanceResponse = await self._client.request(balance_spec(customer_id))
        return result

    async def transactions(self, customer_id: str) -> list[CreditTransactionResponse]:
        """The full history, newest first."""
        result: list[CreditTransactionResponse] = await self._client.request(transactions_spec(customer_id))
        return result
