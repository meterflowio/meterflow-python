"""Subscriptions — one customer on one plan from a date; renews itself."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from .._http import RequestSpec, encode_path_segment
from ..types import SubscriptionCreateRequest, SubscriptionPage, SubscriptionResponse, SubscriptionStatus, SubscriptionUpdateRequest

if TYPE_CHECKING:
    from ..client import AsyncMeterFlow, MeterFlow


def create_spec(body: SubscriptionCreateRequest, idempotency_key: str | None) -> RequestSpec:
    return RequestSpec("POST", "subscriptions", body=body, idempotency_key=idempotency_key)


def list_spec(
    customer_id: str | None, q: str | None, status: Sequence[SubscriptionStatus] | None, limit: int | None, cursor: str | None
) -> RequestSpec:
    return RequestSpec(
        "GET", "subscriptions", query={"customer_id": customer_id, "q": q, "status": status, "limit": limit, "cursor": cursor}
    )


def get_spec(subscription_id: str) -> RequestSpec:
    return RequestSpec("GET", f"subscriptions/{encode_path_segment(subscription_id)}")


def update_spec(subscription_id: str, body: SubscriptionUpdateRequest, idempotency_key: str | None) -> RequestSpec:
    return RequestSpec("PATCH", f"subscriptions/{encode_path_segment(subscription_id)}", body=body, idempotency_key=idempotency_key)


def delete_spec(subscription_id: str) -> RequestSpec:
    return RequestSpec("DELETE", f"subscriptions/{encode_path_segment(subscription_id)}")


class SubscriptionsResource:
    def __init__(self, client: MeterFlow) -> None:
        self._client = client

    def create(self, body: SubscriptionCreateRequest, *, idempotency_key: str | None = None) -> SubscriptionResponse:
        """Put a customer on a plan. ``status`` is ``trialing`` if the plan has trial days, else ``active``."""
        result: SubscriptionResponse = self._client.request(create_spec(body, idempotency_key))
        return result

    def list(
        self,
        *,
        customer_id: str | None = None,
        q: str | None = None,
        status: Sequence[SubscriptionStatus] | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> SubscriptionPage:
        """One page of the project's subscriptions in this key's environment, newest first.

        ``data`` holds the rows and ``next_cursor`` the mark for the page after this one (``None``
        on the last). Pass it back as ``cursor`` unchanged — it is opaque, and nothing but this API
        reads it — with the same filters, which apply before the page is cut. ``customer_id``
        narrows the list to one customer, matched exactly; ``q`` to customers whose id contains it,
        ignoring case (``%`` and ``_`` are literal); ``status`` to subscriptions in one of those statuses.
        """
        result: SubscriptionPage = self._client.request(list_spec(customer_id, q, status, limit, cursor))
        return result

    def get(self, subscription_id: str) -> SubscriptionResponse:
        result: SubscriptionResponse = self._client.request(get_spec(subscription_id))
        return result

    def update(self, subscription_id: str, body: SubscriptionUpdateRequest, *, idempotency_key: str | None = None) -> SubscriptionResponse:
        """Change status or metadata. Cancel with ``{"status": "canceled"}`` — the record stays for history."""
        result: SubscriptionResponse = self._client.request(update_spec(subscription_id, body, idempotency_key))
        return result

    def delete(self, subscription_id: str) -> None:
        """Remove the record entirely — for test data; prefer cancelling in production."""
        self._client.request(delete_spec(subscription_id))


class AsyncSubscriptionsResource:
    def __init__(self, client: AsyncMeterFlow) -> None:
        self._client = client

    async def create(self, body: SubscriptionCreateRequest, *, idempotency_key: str | None = None) -> SubscriptionResponse:
        """Put a customer on a plan. ``status`` is ``trialing`` if the plan has trial days, else ``active``."""
        result: SubscriptionResponse = await self._client.request(create_spec(body, idempotency_key))
        return result

    async def list(
        self,
        *,
        customer_id: str | None = None,
        q: str | None = None,
        status: Sequence[SubscriptionStatus] | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> SubscriptionPage:
        """One page of the project's subscriptions in this key's environment, newest first.

        ``data`` holds the rows and ``next_cursor`` the mark for the page after this one (``None``
        on the last). Pass it back as ``cursor`` unchanged — it is opaque, and nothing but this API
        reads it — with the same filters, which apply before the page is cut. ``customer_id``
        narrows the list to one customer, matched exactly; ``q`` to customers whose id contains it,
        ignoring case (``%`` and ``_`` are literal); ``status`` to subscriptions in one of those statuses.
        """
        result: SubscriptionPage = await self._client.request(list_spec(customer_id, q, status, limit, cursor))
        return result

    async def get(self, subscription_id: str) -> SubscriptionResponse:
        result: SubscriptionResponse = await self._client.request(get_spec(subscription_id))
        return result

    async def update(
        self, subscription_id: str, body: SubscriptionUpdateRequest, *, idempotency_key: str | None = None
    ) -> SubscriptionResponse:
        """Change status or metadata. Cancel with ``{"status": "canceled"}`` — the record stays for history."""
        result: SubscriptionResponse = await self._client.request(update_spec(subscription_id, body, idempotency_key))
        return result

    async def delete(self, subscription_id: str) -> None:
        """Remove the record entirely — for test data; prefer cancelling in production."""
        await self._client.request(delete_spec(subscription_id))
