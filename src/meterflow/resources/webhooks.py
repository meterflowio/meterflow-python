"""Webhook receipts — read-only through the SDK: endpoints are registered in the dashboard.

An endpoint is created, edited and deleted where the signing secret can be shown once and never
again. What an SDK consumer needs at 3am is the other half: which endpoints exist, and what
MeterFlow actually sent them. That is this module.

Not to be confused with :mod:`meterflow.webhook`, which verifies the signature on a webhook your
server has just received. This reads what we sent; that proves we sent it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._http import RequestSpec, encode_path_segment
from ..types import WebhookDeliveryResponse, WebhookResponse

if TYPE_CHECKING:
    from ..client import AsyncMeterFlow, MeterFlow

# Spelled as module-level aliases, where `list` is still the builtin. Inside the class bodies below
# it is not: a method called `list` shadows it for every annotation that follows, so writing
# `list[WebhookDeliveryResponse]` on `deliveries` resolves to the method and mypy rejects it.
# `plans.py` never meets this only because its second method returns a bare type.
WebhookList = list[WebhookResponse]
DeliveryList = list[WebhookDeliveryResponse]


def list_spec() -> RequestSpec:
    # No project_id: the key's own project is the scope, and a query could not widen it.
    return RequestSpec("GET", "webhooks")


def deliveries_spec(webhook_id: str) -> RequestSpec:
    return RequestSpec("GET", f"webhooks/{encode_path_segment(webhook_id)}/deliveries")


class WebhooksResource:
    def __init__(self, client: MeterFlow) -> None:
        self._client = client

    def list(self) -> WebhookList:
        """The endpoints registered for this key's project. Never includes a secret."""
        result: WebhookList = self._client.request(list_spec())
        return result

    def deliveries(self, webhook_id: str) -> DeliveryList:
        """One endpoint's delivery attempts, newest first: what was sent, the HTTP status that came
        back, how many attempts and when the next retry is due.

        Capped at the most recent 100, and scoped to the key's own environment — a ``mf_test_*``
        key reads test receipts, a ``mf_live_*`` key live ones. Another project's webhook is a 404.
        """
        result: DeliveryList = self._client.request(deliveries_spec(webhook_id))
        return result


class AsyncWebhooksResource:
    def __init__(self, client: AsyncMeterFlow) -> None:
        self._client = client

    async def list(self) -> WebhookList:
        """The endpoints registered for this key's project. Never includes a secret."""
        result: WebhookList = await self._client.request(list_spec())
        return result

    async def deliveries(self, webhook_id: str) -> DeliveryList:
        """One endpoint's delivery attempts, newest first: what was sent, the HTTP status that came
        back, how many attempts and when the next retry is due.

        Capped at the most recent 100, and scoped to the key's own environment — a ``mf_test_*``
        key reads test receipts, a ``mf_live_*`` key live ones. Another project's webhook is a 404.
        """
        result: DeliveryList = await self._client.request(deliveries_spec(webhook_id))
        return result
