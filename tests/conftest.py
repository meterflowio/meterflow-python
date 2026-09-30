"""Shared fixtures: a fake API built on ``httpx.MockTransport`` (no network, no extra dependency).

Each test declares routes as ``(method, path) -> handler``; the handler receives the ``httpx.Request``
and returns an ``httpx.Response``. Unrouted requests fail the test — like msw's ``onUnhandledRequest:
"error"`` in the Node suite — so a call that should never reach the network is caught.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from meterflow import AsyncMeterFlow, MeterFlow
from meterflow.types import CreditGrantRequest

BASE = "https://api.meter-flow.com/api/v1"

Handler = Callable[[httpx.Request], httpx.Response]


def api_error(status: int, message: str, **extra: Any) -> httpx.Response:
    """The shape the MeterFlow API actually emits (``app/api/src/exceptions.py``) — not FastAPI's ``{detail}``."""
    return httpx.Response(status, json={"error": {"code": status, "message": message, **extra}})


@dataclass
class FakeApi:
    routes: dict[tuple[str, str], Handler] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def on(self, method: str, path: str, handler: Handler) -> None:
        self.routes[(method.upper(), path)] = handler

    def reply(self, method: str, path: str, status: int = 200, body: Any = None) -> None:
        self.on(method, path, lambda _request: httpx.Response(status, json=body))

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self.routes.get((request.method, request.url.raw_path.decode().split("?")[0]))
        if handler is None:
            raise AssertionError(f"unrouted request: {request.method} {request.url}")
        return handler(request)

    async def handle_async(self, request: httpx.Request) -> httpx.Response:
        return self.handle(request)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def last_json(self) -> Any:
        return json.loads(self.last.content)


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()


@pytest.fixture
def client(api: FakeApi) -> MeterFlow:
    return MeterFlow("mf_test_abc", retries=0, transport=httpx.MockTransport(api.handle))


@pytest.fixture
def async_client(api: FakeApi) -> AsyncMeterFlow:
    return AsyncMeterFlow("mf_test_abc", retries=0, transport=httpx.MockTransport(api.handle_async))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Retries must not slow the suite down: capture the delays instead of waiting them out."""
    delays: list[float] = []

    def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    async def fake_async_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr("meterflow.client._sleep", fake_sleep)
    monkeypatch.setattr("meterflow.client._async_sleep", fake_async_sleep)
    return delays


TX: dict[str, Any] = {
    "id": "tx-1",
    "project_id": "p",
    "customer_external_id": "c",
    "transaction_type": "grant",
    "amount": "10",
    "balance_before": "0",
    "balance_after": "10",
    "description": None,
    "idempotency_key": None,
    "metadata_": {},
    "created_at": "2026-01-01T00:00:00Z",
}

GRANT_BODY: CreditGrantRequest = {"amount": 10, "customer_external_id": "c", "metadata": {}}
