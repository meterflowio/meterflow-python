"""The entitlement answers one client keeps, and the rules for falling back on them. Mirrors ``sdks/node/src/utils/entitlement-cache.ts``.

Each answer is fresh for the ``max-age`` the API sends and kept past it as the fallback for an outage.
Bounded, least recently used out first.
"""

from __future__ import annotations

import re
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from .errors import MeterFlowError, RateLimitError, ServerError

# How many answers one client keeps; the least recently used goes first past it.
MAX_CACHED_ENTITLEMENTS = 1_000

EntitlementDefault = Literal["allow", "deny"]

# The clock answers are aged by; an indirection so tests can step it.
_now = time.monotonic

_MAX_AGE = re.compile(r"\bmax-age=(\d+)", re.IGNORECASE)
_NO_STORE = re.compile(r"\bno-(store|cache)\b", re.IGNORECASE)


@dataclass(frozen=True)
class EntitlementFallbackContext:
    """Which call fell back, and to what, as ``on_error`` is told.

    customer_id: the customer the call was for.
    feature: the feature checked; None for ``entitlements.get()``.
    fallback: ``stale``, the last answer past its ``max-age``; ``default``, the configured ``entitlement_defaults`` entry.
    """

    customer_id: str
    feature: str | None
    fallback: Literal["stale", "default"]


OnEntitlementError = Callable[[Exception, EntitlementFallbackContext], None]


@dataclass(frozen=True)
class CacheRead:
    """An answer found in the cache, and whether it is still fresh."""

    value: Any
    fresh: bool


@dataclass
class _CachedAnswer:
    customer_id: str
    value: Any
    fresh_until: float


def max_age_seconds(header: str | None) -> int:
    """The seconds a response may be reused for: its ``max-age``; 0 when absent, ``no-store`` / ``no-cache``, or naming none.

    header: the response's ``Cache-Control`` value, or None.
    """
    if not header or _NO_STORE.search(header):
        return 0
    match = _MAX_AGE.search(header)
    return int(match.group(1)) if match else 0


def is_outage(error: BaseException) -> bool:
    """Whether a failed call is MeterFlow being unreachable rather than an answer: no response at all, a 5xx after the retries, or a 429.

    error: what the call raised.
    """
    if not isinstance(error, MeterFlowError):
        return True
    return isinstance(error, ServerError | RateLimitError)


class EntitlementCache:
    """The entitlement answers one client has read, each fresh for the API's ``max-age`` and kept past it as an outage fallback."""

    def __init__(self) -> None:
        self._answers: OrderedDict[str, _CachedAnswer] = OrderedDict()

    def read(self, key: str) -> CacheRead | None:
        """The answer stored under ``key``, with whether it is still fresh; None when there is none.

        key: the call's cache key.
        """
        cached = self._answers.get(key)
        if cached is None:
            return None
        self._answers.move_to_end(key)
        return CacheRead(cached.value, _now() < cached.fresh_until)

    def write(self, key: str, customer_id: str, value: Any, seconds: int) -> None:
        """Keep an answer for ``seconds``; nothing is kept when that is 0.

        key: the call's cache key.
        customer_id: whose answer it is, so a write for them can expire it.
        value: the answer.
        seconds: how long it stays fresh.
        """
        if seconds <= 0:
            return
        self._answers[key] = _CachedAnswer(customer_id, value, _now() + seconds)
        self._answers.move_to_end(key)
        if len(self._answers) > MAX_CACHED_ENTITLEMENTS:
            self._answers.popitem(last=False)

    def invalidate(self, customer_id: str) -> None:
        """Make every answer for a customer stale, after a write that changed what they may do. They stay as an outage fallback.

        customer_id: the customer written for.
        """
        for cached in self._answers.values():
            if cached.customer_id == customer_id:
                cached.fresh_until = 0.0


def expire_entitlements(cache: EntitlementCache | None, customer_ids: list[str]) -> None:
    """Make the cached answers of every customer a successful write touched stale; nothing when the cache is off.

    cache: the client's cache, or None.
    customer_ids: the customers written for, repeats allowed.
    """
    if cache is None:
        return
    for customer_id in set(customer_ids):
        cache.invalidate(customer_id)
