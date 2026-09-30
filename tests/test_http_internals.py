from __future__ import annotations

import httpx

from meterflow import MeterFlow
from meterflow._http import RequestSpec, _async_sleep, build_params, request_kwargs
from tests.conftest import FakeApi


def test_per_call_timeout_is_forwarded_to_httpx() -> None:
    assert request_kwargs("mf_test_x", RequestSpec("GET", "plans", timeout=2.5))["timeout"] == 2.5
    assert "timeout" not in request_kwargs("mf_test_x", RequestSpec("GET", "plans"))


def test_booleans_become_lowercase_strings_like_the_node_sdk() -> None:
    assert build_params({"flag": True, "other": False, "n": 3, "skip": None}) == {"flag": "true", "other": "false", "n": "3"}


def test_request_with_timeout_reaches_the_transport(api: FakeApi, client: MeterFlow) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    api.on("GET", "/api/v1/plans", handler)
    assert client.request(RequestSpec("GET", "plans", timeout=1.0)) == []
    assert seen[0].extensions["timeout"]["read"] == 1.0


async def test_async_sleep_helper_really_sleeps() -> None:
    await _async_sleep(0)  # the real helper; the fixture replaces it everywhere else
