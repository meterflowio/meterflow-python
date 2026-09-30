"""Subscriptions — one customer on one plan from a date; renews itself."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._http import RequestSpec, encode_path_segment
from ..types import SubscriptionCreateRequest, SubscriptionResponse, SubscriptionUpdateRequest

if TYPE_CHECKING:
    from ..client import AsyncMeterFlow, MeterFlow


def create_spec(body: SubscriptionCreateRequest, idempotency_key: str | None) -> RequestSpec:
    return RequestSpec("POST", "subscriptions", body=body, idempotency_key=idempotency_key)


def list_spec(customer_id: str | None) -> RequestSpec:
    return RequestSpec("GET", "subscriptions", query={"customer_id": customer_id})


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

    def list(self, *, customer_id: str | None = None) -> list[SubscriptionResponse]:
        """The project's subscriptions in this key's environment, optionally one customer's."""
        result: list[SubscriptionResponse] = self._client.request(list_spec(customer_id))
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

    async def list(self, *, customer_id: str | None = None) -> list[SubscriptionResponse]:
        """The project's subscriptions in this key's environment, optionally one customer's."""
        result: list[SubscriptionResponse] = await self._client.request(list_spec(customer_id))
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
