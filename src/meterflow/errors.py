"""Typed error hierarchy — one class per HTTP outcome, mirroring the Node SDK one-to-one.

Every error carries the API's ``X-Request-ID`` (``request_id``) so a support ticket can point at the
exact request, plus ``status_code``, ``error_type`` and ``retryable`` for structured logging.
"""

from __future__ import annotations

from typing import TypedDict


class ValidationFieldError(TypedDict):
    """One field the API rejected, as returned in a 422's ``error.fields``."""

    field: str
    message: str


class MeterFlowError(Exception):
    def __init__(
        self,
        message: str,
        error_type: str = "request_error",
        *,
        retryable: bool = False,
        request_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.retryable = retryable
        self.request_id = request_id
        self.status_code = status_code

    def __str__(self) -> str:
        return self.message


class AuthError(MeterFlowError):
    """401 / 403 — the key is missing, invalid, revoked or not allowed to do this."""

    def __init__(self, message: str, *, request_id: str | None = None, status_code: int = 401) -> None:
        super().__init__(message, "auth_error", retryable=False, request_id=request_id, status_code=status_code)


class NotFoundError(MeterFlowError):
    """404 — no such customer, plan, subscription… or an unknown feature key (a typo, not a plan)."""

    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        super().__init__(message, "not_found", retryable=False, request_id=request_id, status_code=404)


class InsufficientCreditsError(MeterFlowError):
    """402 — a deduction the balance cannot cover. A business outcome, not a failure: prompt a top-up."""

    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        super().__init__(message, "insufficient_credits", retryable=False, request_id=request_id, status_code=402)


class ConflictError(MeterFlowError):
    """409 — the write clashes with current state (e.g. the project is deactivated)."""

    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        super().__init__(message, "conflict", retryable=False, request_id=request_id, status_code=409)


class ValidationError(MeterFlowError):
    """422 — the API rejected the payload. ``fields`` holds the per-field detail (empty when none was sent)."""

    def __init__(self, message: str, *, request_id: str | None = None, fields: list[ValidationFieldError] | None = None) -> None:
        super().__init__(message, "validation_error", retryable=False, request_id=request_id, status_code=422)
        self.fields: list[ValidationFieldError] = list(fields or [])


class PayloadTooLargeError(MeterFlowError):
    """413 — well-formed but too big; today only ``usage.record_batch`` above ``MAX_BATCH_EVENTS``.

    Never retried: the same payload would be refused again. Split it at the call site.
    """

    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        super().__init__(message, "payload_too_large", retryable=False, request_id=request_id, status_code=413)


class RateLimitError(MeterFlowError):
    """429 — retried automatically after the server's ``Retry-After`` (seconds, exposed as ``retry_after``)."""

    def __init__(self, message: str, *, retry_after: int | None = None, request_id: str | None = None) -> None:
        super().__init__(message, "rate_limit", retryable=True, request_id=request_id, status_code=429)
        self.retry_after = retry_after


class ServerError(MeterFlowError):
    """5xx — MeterFlow's side; retried automatically with backoff."""

    def __init__(self, message: str, *, request_id: str | None = None, status_code: int = 500) -> None:
        super().__init__(message, "server_error", retryable=True, request_id=request_id, status_code=status_code)
