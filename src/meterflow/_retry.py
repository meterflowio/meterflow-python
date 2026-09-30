"""Retry policy shared by the sync and async clients.

The policy only *decides* — how long to wait before attempt N+1, or that the caller should give up.
The clients do the sleeping (``time.sleep`` vs ``asyncio.sleep``), so the backoff maths lives once.
Mirrors the Node SDK: exponential base (1 s × factor^attempt, capped), ±25 % jitter, and a 429's
``Retry-After`` taken verbatim instead of the computed delay.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .errors import MeterFlowError, RateLimitError


@dataclass(frozen=True)
class RetryPolicy:
    retries: int = 3
    factor: float = 2.0
    jitter: bool = True
    max_delay_seconds: float = 10.0

    def should_retry(self, error: BaseException) -> bool:
        """API errors say for themselves whether a retry can help; anything else is a transport failure and can."""
        if isinstance(error, MeterFlowError):
            return error.retryable
        return True

    def delay_before_retry(self, attempt: int, error: BaseException) -> float | None:
        """Seconds to wait before retrying ``attempt`` (0-based), or ``None`` when the caller must re-raise."""
        is_last = attempt >= self.retries
        if is_last or not self.should_retry(error):
            return None
        if isinstance(error, RateLimitError) and error.retry_after is not None:
            return float(error.retry_after)
        base = min(1.0 * (self.factor**attempt), self.max_delay_seconds)
        return base * (0.75 + random.random() * 0.5) if self.jitter else base  # noqa: S311 — jitter, not security
