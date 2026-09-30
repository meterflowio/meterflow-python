"""Plans — read-only through the SDK: pricing is managed by humans in the dashboard."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._http import RequestSpec, encode_path_segment
from ..types import PlanResponse

if TYPE_CHECKING:
    from ..client import AsyncMeterFlow, MeterFlow


def list_spec(project_id: str | None) -> RequestSpec:
    return RequestSpec("GET", "plans", query={"project_id": project_id})


def get_spec(plan_id: str, project_id: str | None) -> RequestSpec:
    return RequestSpec("GET", f"plans/{encode_path_segment(plan_id)}", query={"project_id": project_id})


class PlansResource:
    def __init__(self, client: MeterFlow) -> None:
        self._client = client

    def list(self, *, project_id: str | None = None) -> list[PlanResponse]:
        """The project's plans — render your pricing page from this so it can never drift from billing."""
        result: list[PlanResponse] = self._client.request(list_spec(project_id))
        return result

    def get(self, plan_id: str, *, project_id: str | None = None) -> PlanResponse:
        """One plan, including its per-meter limits and feature keys."""
        result: PlanResponse = self._client.request(get_spec(plan_id, project_id))
        return result


class AsyncPlansResource:
    def __init__(self, client: AsyncMeterFlow) -> None:
        self._client = client

    async def list(self, *, project_id: str | None = None) -> list[PlanResponse]:
        """The project's plans — render your pricing page from this so it can never drift from billing."""
        result: list[PlanResponse] = await self._client.request(list_spec(project_id))
        return result

    async def get(self, plan_id: str, *, project_id: str | None = None) -> PlanResponse:
        """One plan, including its per-meter limits and feature keys."""
        result: PlanResponse = await self._client.request(get_spec(plan_id, project_id))
        return result
