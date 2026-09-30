from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from meterflow import verify_webhook
from meterflow.webhook import verify_webhook as verify_webhook_from_module


def sign(body: str, secret: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


SECRET = "test-secret"
BODY = json.dumps({"event": "credit.granted", "amount": 100})
VALID = sign(BODY, SECRET)


def test_exported_from_root_and_webhook_module() -> None:
    assert verify_webhook is verify_webhook_from_module


def test_valid_signature_str_and_bytes_body() -> None:
    assert verify_webhook(BODY, VALID, SECRET) is True
    assert verify_webhook(BODY.encode("utf-8"), VALID, SECRET) is True


def test_wrong_signature() -> None:
    assert verify_webhook(BODY, "deadbeef" * 8, SECRET) is False


def test_wrong_secret() -> None:
    assert verify_webhook(BODY, sign(BODY, "wrong-secret"), SECRET) is False


def test_tampered_body() -> None:
    assert verify_webhook(json.dumps({"event": "credit.granted", "amount": 999}), VALID, SECRET) is False


@pytest.mark.parametrize("signature", ["abc", "", "not-hex-at-all"])
def test_short_empty_or_malformed_signature_is_false_never_raises(signature: str) -> None:
    assert verify_webhook(BODY, signature, SECRET) is False


def test_deterministic() -> None:
    assert verify_webhook(BODY, VALID, SECRET) is True
    assert verify_webhook(BODY, VALID, SECRET) is True


def test_signature_is_64_hex_chars() -> None:
    assert len(VALID) == 64
    assert all(char in "0123456789abcdef" for char in VALID)


@pytest.mark.parametrize("body", ["", "€™", "\x00\x01\x02"])
def test_handles_empty_unicode_and_binary_like_bodies(body: str) -> None:
    signature = sign(body, SECRET)
    assert verify_webhook(body, signature, SECRET) is True
    assert verify_webhook(body, "wrong" + signature[5:], SECRET) is False


def test_matches_the_api_signer_byte_for_byte() -> None:
    """The scheme is HMAC-SHA256 over the UTF-8 body, hex digest — exactly ``webhook_signer.sign_webhook``."""
    payload = json.dumps({"event": "limit.reached", "environment": "live", "customer_id": "user-842"})
    assert verify_webhook(
        payload.encode("utf-8"), hmac.new(SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest(), SECRET
    )
