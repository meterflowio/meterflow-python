"""The HTTP layer both clients share: URL/header building, error-body parsing, status → error mapping.

Only the *waiting* differs between sync and async, so the request loops live in ``client.py`` and
everything they call lives here, once. Mirrors ``sdks/node/src/utils/http.ts``.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

from ._version import __version__
from .errors import (
    AuthError,
    ConflictError,
    InsufficientCreditsError,
    MeterFlowError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitError,
    ServerError,
    ValidationError,
    ValidationFieldError,
)

USER_AGENT = f"meterflow-python/{__version__}"

QueryValue = str | int | float | bool | None

# Indirections so tests can make the retry loop instantaneous without touching the clock.
_sleep = time.sleep


async def _async_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


@dataclass(frozen=True)
class RequestSpec:
    """One API call, described by a resource method and executed by a client."""

    method: str
    path: str
    body: Any = None
    query: dict[str, QueryValue] = field(default_factory=dict)
    idempotency_key: str | None = None
    timeout: float | None = None


def encode_path_segment(value: str) -> str:
    """Customer ids are caller-chosen strings (emails, ``user/42``…) — they must never split the path."""
    return quote(value, safe="")


def build_headers(api_key: str, spec: RequestSpec) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key}", "User-Agent": USER_AGENT, "Accept": "application/json"}
    if spec.body is not None:
        headers["Content-Type"] = "application/json"
    if spec.idempotency_key:
        headers["Idempotency-Key"] = spec.idempotency_key
    return headers


def build_params(query: dict[str, QueryValue]) -> dict[str, str]:
    """Unset (``None``) filters are simply not sent; booleans go as ``true``/``false`` like the Node SDK."""
    params: dict[str, str] = {}
    for key, value in query.items():
        if value is None:
            continue
        params[key] = ("true" if value else "false") if isinstance(value, bool) else str(value)
    return params


@dataclass(frozen=True)
class ParsedError:
    message: str
    fields: list[ValidationFieldError]


def _is_field_error(value: object) -> bool:
    return isinstance(value, dict) and isinstance(value.get("field"), str) and isinstance(value.get("message"), str)


def parse_error_body(response: httpx.Response) -> ParsedError:
    """The API answers every error as ``{"error": {"code", "message", "fields"?}}`` (``app/api/src/exceptions.py``).

    ``detail`` is FastAPI's default shape, kept as a fallback so an unexpected passthrough still
    yields a readable message rather than a JSON blob.
    """
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return ParsedError(response.reason_phrase or f"HTTP {response.status_code}", [])
    if not isinstance(payload, dict):
        return ParsedError(json.dumps(payload), [])
    error = payload.get("error")
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        raw_fields = error.get("fields")
        fields: list[ValidationFieldError] = (
            [{"field": item["field"], "message": item["message"]} for item in raw_fields if _is_field_error(item)]
            if isinstance(raw_fields, list)
            else []
        )
        # A 422's headline is always "Validation failed"; the field list is what the caller needs.
        detail = "; ".join(f"{item['field']}: {item['message']}" for item in fields)
        message = f"{error['message']}: {detail}" if detail else error["message"]
        return ParsedError(message, fields)
    detail_value = payload.get("detail")
    if isinstance(detail_value, str):
        return ParsedError(detail_value, [])
    return ParsedError(json.dumps(payload), [])


def map_response_error(response: httpx.Response) -> MeterFlowError:
    status = response.status_code
    parsed = parse_error_body(response)
    request_id = response.headers.get("x-request-id")
    message, fields = parsed.message, parsed.fields
    if status in (401, 403):
        return AuthError(message, request_id=request_id, status_code=status)
    if status == 402:
        return InsufficientCreditsError(message, request_id=request_id)
    if status == 404:
        return NotFoundError(message, request_id=request_id)
    if status == 409:
        return ConflictError(message, request_id=request_id)
    if status == 413:
        return PayloadTooLargeError(message, request_id=request_id)
    if status == 422:
        return ValidationError(message, request_id=request_id, fields=fields)
    if status == 429:
        retry_after_raw = response.headers.get("retry-after")
        retry_after = int(retry_after_raw) if retry_after_raw is not None and retry_after_raw.strip().isdigit() else None
        return RateLimitError(message, retry_after=retry_after, request_id=request_id)
    if status >= 500:
        return ServerError(message, request_id=request_id, status_code=status)
    return MeterFlowError(message, "request_error", retryable=False, request_id=request_id, status_code=status)


def decode_response(response: httpx.Response) -> Any:
    """2xx → parsed JSON; ``204`` / an empty body → ``None`` (``subscriptions.delete``)."""
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def request_kwargs(api_key: str, spec: RequestSpec) -> dict[str, Any]:
    """Everything ``httpx.Client.request`` / ``AsyncClient.request`` needs beyond the method and path."""
    kwargs: dict[str, Any] = {"headers": build_headers(api_key, spec), "params": build_params(spec.query)}
    if spec.body is not None:
        kwargs["content"] = json.dumps(spec.body).encode("utf-8")
    if spec.timeout is not None:
        kwargs["timeout"] = spec.timeout
    return kwargs
