"""Entitlements — ask BEFORE doing the work.

``check()`` is where a hard limit says no; recording usage afterwards never blocks, so an app that
skips this call gets no enforcement at all — only an honest ledger.

``allowed: False`` is a normal answer, not an error: the call returns and ``reason`` says why
(``no_subscription``, ``not_in_plan``, ``hard_limit_reached``, ``insufficient_credits``). A feature
key the project does not know at all is a 404 → ``NotFoundError``, because that is a typo, not a plan.

Both calls return ``Cache-Control: private, max-age=15`` — cache per customer for a few seconds on
hot paths rather than calling on every request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._http import RequestSpec, encode_path_segment
from ..types import EntitlementResponse, EntitlementsResponse

if TYPE_CHECKING:
    from ..client import AsyncMeterFlow, MeterFlow


def get_spec(customer_id: str) -> RequestSpec:
    return RequestSpec("GET", f"entitlements/{encode_path_segment(customer_id)}")


def check_spec(customer_id: str, feature: str, quantity: int | None) -> RequestSpec:
    return RequestSpec("GET", f"entitlements/{encode_path_segment(customer_id)}/check", query={"feature": feature, "quantity": quantity})


class EntitlementsResource:
    def __init__(self, client: MeterFlow) -> None:
        self._client = client

    def get(self, customer_id: str) -> EntitlementsResponse:
        """Every feature on the customer's plan, with this period's usage. Empty ``entitlements`` without a subscription."""
        result: EntitlementsResponse = self._client.request(get_spec(customer_id))
        return result

    def check(self, customer_id: str, feature: str, *, quantity: int | None = None) -> EntitlementResponse:
        """May this customer use ``feature`` (``quantity`` more units of it — "may they do 5 more?") right now?"""
        result: EntitlementResponse = self._client.request(check_spec(customer_id, feature, quantity))
        return result


class AsyncEntitlementsResource:
    def __init__(self, client: AsyncMeterFlow) -> None:
        self._client = client

    async def get(self, customer_id: str) -> EntitlementsResponse:
        """Every feature on the customer's plan, with this period's usage. Empty ``entitlements`` without a subscription."""
        result: EntitlementsResponse = await self._client.request(get_spec(customer_id))
        return result

    async def check(self, customer_id: str, feature: str, *, quantity: int | None = None) -> EntitlementResponse:
        """May this customer use ``feature`` (``quantity`` more units of it — "may they do 5 more?") right now?"""
        result: EntitlementResponse = await self._client.request(check_spec(customer_id, feature, quantity))
        return result
