"""Credits — an append-only ledger per customer: grant up, deduct down, never edited in place; holds set credits aside."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._entitlement_cache import expire_entitlements
from .._http import RequestSpec, encode_path_segment
from ..types import (
    CreditBalanceResponse,
    CreditDeductRequest,
    CreditGrantRequest,
    CreditReservationConfirmRequest,
    CreditReservationRequest,
    CreditReservationResponse,
    CreditTransactionPage,
    CreditTransactionResponse,
)

if TYPE_CHECKING:
    from ..client import AsyncMeterFlow, MeterFlow


def grant_spec(body: CreditGrantRequest, idempotency_key: str | None) -> RequestSpec:
    return RequestSpec("POST", "credits/grant", body=body, idempotency_key=idempotency_key)


def deduct_spec(body: CreditDeductRequest, idempotency_key: str | None) -> RequestSpec:
    return RequestSpec("POST", "credits/deduct", body=body, idempotency_key=idempotency_key)


def reserve_spec(body: CreditReservationRequest, idempotency_key: str | None) -> RequestSpec:
    return RequestSpec("POST", "credits/reservations", body=body, idempotency_key=idempotency_key)


def confirm_reservation_spec(reservation_id: str, body: CreditReservationConfirmRequest | None) -> RequestSpec:
    return RequestSpec("POST", f"credits/reservations/{encode_path_segment(reservation_id)}/confirm", body=body or {})


def release_reservation_spec(reservation_id: str) -> RequestSpec:
    return RequestSpec("POST", f"credits/reservations/{encode_path_segment(reservation_id)}/release")


def reservation_spec(reservation_id: str) -> RequestSpec:
    return RequestSpec("GET", f"credits/reservations/{encode_path_segment(reservation_id)}")


def balance_spec(customer_id: str) -> RequestSpec:
    return RequestSpec("GET", f"credits/{encode_path_segment(customer_id)}/balance")


def transactions_spec(customer_id: str, limit: int | None, cursor: str | None) -> RequestSpec:
    return RequestSpec("GET", f"credits/{encode_path_segment(customer_id)}/transactions", query={"limit": limit, "cursor": cursor})


class CreditsResource:
    def __init__(self, client: MeterFlow) -> None:
        self._client = client

    def grant(self, body: CreditGrantRequest, *, idempotency_key: str | None = None) -> CreditTransactionResponse:
        """Add credits (plan renewals, top-ups, goodwill). Returns the ledger line. The customer's cached entitlement answers go stale."""
        result: CreditTransactionResponse = self._client.request(grant_spec(body, idempotency_key))
        expire_entitlements(self._client.entitlement_cache, [body["customer_external_id"]])
        return result

    def deduct(self, body: CreditDeductRequest, *, idempotency_key: str | None = None) -> CreditTransactionResponse:
        """Remove credits. Raises ``InsufficientCreditsError`` (402) rather than take the customer below zero.

        The customer's cached entitlement answers go stale.
        """
        result: CreditTransactionResponse = self._client.request(deduct_spec(body, idempotency_key))
        expire_entitlements(self._client.entitlement_cache, [body["customer_external_id"]])
        return result

    def reserve(self, body: CreditReservationRequest, *, idempotency_key: str | None = None) -> CreditReservationResponse:
        """Hold credits until confirmed, released or ``ttl_seconds`` (default 300) runs out; the balance stays, ``available`` drops.

        Raises ``InsufficientCreditsError`` (402) when the available credits cannot cover it. The customer's cached entitlement
        answers go stale.

        body: the customer, the amount, how long to hold it, a description and metadata.
        idempotency_key: makes a retried hold the same hold.
        """
        result: CreditReservationResponse = self._client.request(reserve_spec(body, idempotency_key))
        expire_entitlements(self._client.entitlement_cache, [body["customer_external_id"]])
        return result

    def confirm_reservation(self, reservation_id: str, body: CreditReservationConfirmRequest | None = None) -> CreditReservationResponse:
        """Take some or all of a hold from the balance, as one ``deduct`` ledger row, and free the rest.

        Raises ``ConflictError`` (409) unless it is still held, ``ValidationError`` (422) above the amount held. The customer's
        cached entitlement answers go stale.

        reservation_id: the hold's ``id``.
        body: ``amount`` to take; the whole hold when left out.
        """
        result: CreditReservationResponse = self._client.request(confirm_reservation_spec(reservation_id, body))
        expire_entitlements(self._client.entitlement_cache, [result["customer_external_id"]])
        return result

    def release_reservation(self, reservation_id: str) -> CreditReservationResponse:
        """Free a hold with nothing taken; an expired hold answers ``status: "expired"``, a settled one raises ``ConflictError`` (409).

        The customer's cached entitlement answers go stale.

        reservation_id: the hold's ``id``.
        """
        result: CreditReservationResponse = self._client.request(release_reservation_spec(reservation_id))
        expire_entitlements(self._client.entitlement_cache, [result["customer_external_id"]])
        return result

    def reservation(self, reservation_id: str) -> CreditReservationResponse:
        """One hold and how it ended: ``held``, ``confirmed``, ``released``, or ``expired`` once held past ``expires_at``.

        reservation_id: the hold's ``id``.
        """
        result: CreditReservationResponse = self._client.request(reservation_spec(reservation_id))
        return result

    def balance(self, customer_id: str) -> CreditBalanceResponse:
        """The customer's current position — amounts are decimal strings."""
        result: CreditBalanceResponse = self._client.request(balance_spec(customer_id))
        return result

    def transactions(self, customer_id: str, *, limit: int | None = None, cursor: str | None = None) -> CreditTransactionPage:
        """One page of the ledger, newest first.

        The ledger grows with every charge, so it is read a page at a time: ``data`` holds the rows
        and ``next_cursor`` the mark for the page after this one (``None`` on the last). Pass it
        back as ``cursor`` unchanged — it is opaque, and nothing but this API reads it.
        """
        result: CreditTransactionPage = self._client.request(transactions_spec(customer_id, limit, cursor))
        return result


class AsyncCreditsResource:
    def __init__(self, client: AsyncMeterFlow) -> None:
        self._client = client

    async def grant(self, body: CreditGrantRequest, *, idempotency_key: str | None = None) -> CreditTransactionResponse:
        """Add credits (plan renewals, top-ups, goodwill). Returns the ledger line. The customer's cached entitlement answers go stale."""
        result: CreditTransactionResponse = await self._client.request(grant_spec(body, idempotency_key))
        expire_entitlements(self._client.entitlement_cache, [body["customer_external_id"]])
        return result

    async def deduct(self, body: CreditDeductRequest, *, idempotency_key: str | None = None) -> CreditTransactionResponse:
        """Remove credits. Raises ``InsufficientCreditsError`` (402) rather than take the customer below zero.

        The customer's cached entitlement answers go stale.
        """
        result: CreditTransactionResponse = await self._client.request(deduct_spec(body, idempotency_key))
        expire_entitlements(self._client.entitlement_cache, [body["customer_external_id"]])
        return result

    async def reserve(self, body: CreditReservationRequest, *, idempotency_key: str | None = None) -> CreditReservationResponse:
        """Hold credits until confirmed, released or ``ttl_seconds`` (default 300) runs out; the balance stays, ``available`` drops.

        Raises ``InsufficientCreditsError`` (402) when the available credits cannot cover it. The customer's cached entitlement
        answers go stale.

        body: the customer, the amount, how long to hold it, a description and metadata.
        idempotency_key: makes a retried hold the same hold.
        """
        result: CreditReservationResponse = await self._client.request(reserve_spec(body, idempotency_key))
        expire_entitlements(self._client.entitlement_cache, [body["customer_external_id"]])
        return result

    async def confirm_reservation(
        self, reservation_id: str, body: CreditReservationConfirmRequest | None = None
    ) -> CreditReservationResponse:
        """Take some or all of a hold from the balance, as one ``deduct`` ledger row, and free the rest.

        Raises ``ConflictError`` (409) unless it is still held, ``ValidationError`` (422) above the amount held. The customer's
        cached entitlement answers go stale.

        reservation_id: the hold's ``id``.
        body: ``amount`` to take; the whole hold when left out.
        """
        result: CreditReservationResponse = await self._client.request(confirm_reservation_spec(reservation_id, body))
        expire_entitlements(self._client.entitlement_cache, [result["customer_external_id"]])
        return result

    async def release_reservation(self, reservation_id: str) -> CreditReservationResponse:
        """Free a hold with nothing taken; an expired hold answers ``status: "expired"``, a settled one raises ``ConflictError`` (409).

        The customer's cached entitlement answers go stale.

        reservation_id: the hold's ``id``.
        """
        result: CreditReservationResponse = await self._client.request(release_reservation_spec(reservation_id))
        expire_entitlements(self._client.entitlement_cache, [result["customer_external_id"]])
        return result

    async def reservation(self, reservation_id: str) -> CreditReservationResponse:
        """One hold and how it ended: ``held``, ``confirmed``, ``released``, or ``expired`` once held past ``expires_at``.

        reservation_id: the hold's ``id``.
        """
        result: CreditReservationResponse = await self._client.request(reservation_spec(reservation_id))
        return result

    async def balance(self, customer_id: str) -> CreditBalanceResponse:
        """The customer's current position — amounts are decimal strings."""
        result: CreditBalanceResponse = await self._client.request(balance_spec(customer_id))
        return result

    async def transactions(self, customer_id: str, *, limit: int | None = None, cursor: str | None = None) -> CreditTransactionPage:
        """One page of the ledger, newest first.

        The ledger grows with every charge, so it is read a page at a time: ``data`` holds the rows
        and ``next_cursor`` the mark for the page after this one (``None`` on the last). Pass it
        back as ``cursor`` unchanged — it is opaque, and nothing but this API reads it.
        """
        result: CreditTransactionPage = await self._client.request(transactions_spec(customer_id, limit, cursor))
        return result
