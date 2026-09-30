"""Webhook signature verification — HMAC-SHA256 over the raw body, hex-encoded, timing-safe.

Byte-for-byte the same scheme as the Node SDK's ``verifyWebhook`` and the API's signer: a delivery
signed by MeterFlow verifies here with the webhook's secret, and nothing else does.
"""

from __future__ import annotations

import hashlib
import hmac


def verify_webhook(body: bytes | str, signature: str, secret: str) -> bool:
    """Return ``True`` when ``signature`` (the ``X-MeterFlow-Signature`` header) matches ``body``.

    Pass the **raw** request body — re-serialised JSON changes whitespace and key order and will
    not match. Never raises on bad input: an empty, short or malformed signature is simply ``False``.
    """
    raw = body.encode("utf-8") if isinstance(body, str) else body
    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
