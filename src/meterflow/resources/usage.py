"""Usage events — "this customer just did this thing, this much", matched to a meter by ``event_name``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._http import RequestSpec, encode_path_segment
from ..errors import PayloadTooLargeError
from ..types import UsageEventRequest, UsageEventResponse, UsageSummaryResponse

if TYPE_CHECKING:
    from ..client import AsyncMeterFlow, MeterFlow

# The API refuses a batch above this with 413. The SDK checks it before sending so an oversized
# batch fails instantly, offline, with the same ``PayloadTooLargeError`` — and it does NOT split
# the batch for you: one call is one request with one idempotency key, and silently turning it
# into N requests would leave partial success indistinguishable from failure. Chunk at the call
# site, where you can pick a key per chunk.
MAX_BATCH_EVENTS = 500


def record_spec(body: UsageEventRequest, idempotency_key: str | None) -> RequestSpec:
    return RequestSpec("POST", "usage/events", body=body, idempotency_key=idempotency_key)


def record_batch_spec(events: list[UsageEventRequest], idempotency_key: str | None) -> RequestSpec:
    if len(events) > MAX_BATCH_EVENTS:
        raise PayloadTooLargeError(f"A batch may contain at most {MAX_BATCH_EVENTS} events; this one has {len(events)}. Split it.")
    return RequestSpec("POST", "usage/events/batch", body={"events": events}, idempotency_key=idempotency_key)


def summary_spec(customer_id: str, meter_id: str | None, from_: str | None, to: str | None) -> RequestSpec:
    return RequestSpec("GET", f"usage/{encode_path_segment(customer_id)}", query={"meter_id": meter_id, "from_": from_, "to": to})


class UsageResource:
    def __init__(self, client: MeterFlow) -> None:
        self._client = client

    def record(self, body: UsageEventRequest, *, idempotency_key: str | None = None) -> UsageEventResponse:
        """Record one event. Returns immediately (``processed: False``); totals materialise moments later."""
        result: UsageEventResponse = self._client.request(record_spec(body, idempotency_key))
        return result

    def record_batch(self, events: list[UsageEventRequest], *, idempotency_key: str | None = None) -> list[UsageEventResponse]:
        """Record up to ``MAX_BATCH_EVENTS`` events in one request. A larger list is refused locally, never sent."""
        result: list[UsageEventResponse] = self._client.request(record_batch_spec(events, idempotency_key))
        return result

    def summary(
        self, customer_id: str, *, meter_id: str | None = None, from_: str | None = None, to: str | None = None
    ) -> UsageSummaryResponse:
        """A customer's usage broken down by meter. ``from_`` keeps the API's trailing underscore."""
        result: UsageSummaryResponse = self._client.request(summary_spec(customer_id, meter_id, from_, to))
        return result


class AsyncUsageResource:
    def __init__(self, client: AsyncMeterFlow) -> None:
        self._client = client

    async def record(self, body: UsageEventRequest, *, idempotency_key: str | None = None) -> UsageEventResponse:
        """Record one event. Returns immediately (``processed: False``); totals materialise moments later."""
        result: UsageEventResponse = await self._client.request(record_spec(body, idempotency_key))
        return result

    async def record_batch(self, events: list[UsageEventRequest], *, idempotency_key: str | None = None) -> list[UsageEventResponse]:
        """Record up to ``MAX_BATCH_EVENTS`` events in one request. A larger list is refused locally, never sent."""
        result: list[UsageEventResponse] = await self._client.request(record_batch_spec(events, idempotency_key))
        return result

    async def summary(
        self, customer_id: str, *, meter_id: str | None = None, from_: str | None = None, to: str | None = None
    ) -> UsageSummaryResponse:
        """A customer's usage broken down by meter. ``from_`` keeps the API's trailing underscore."""
        result: UsageSummaryResponse = await self._client.request(summary_spec(customer_id, meter_id, from_, to))
        return result
