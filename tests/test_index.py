from __future__ import annotations

import meterflow
from meterflow import MAX_BATCH_EVENTS, __version__


def test_public_surface() -> None:
    expected = {
        "__version__",
        "MeterFlow",
        "AsyncMeterFlow",
        "ClientOptions",
        "MeterFlowError",
        "AuthError",
        "NotFoundError",
        "InsufficientCreditsError",
        "ConflictError",
        "PayloadTooLargeError",
        "ValidationError",
        "ValidationFieldError",
        "RateLimitError",
        "ServerError",
        "MAX_BATCH_EVENTS",
        "verify_webhook",
    }
    assert set(meterflow.__all__) == expected
    for name in expected:
        assert hasattr(meterflow, name)


def test_version_is_a_semver_string() -> None:
    major, minor, patch = __version__.split(".")
    assert all(part.isdigit() for part in (major, minor, patch))


def test_batch_cap_matches_the_api() -> None:
    assert MAX_BATCH_EVENTS == 500


def test_types_module_exposes_the_sdk_facing_shapes_only() -> None:
    from meterflow import types

    assert {"CreditGrantRequest", "EntitlementResponse", "PlanResponse", "UsageEventRequest", "SubscriptionResponse"} <= set(types.__all__)
    assert not {"ApiKeyCreateRequest", "OrganizationResponse", "WebhookCreateRequest", "MeterCreateRequest"} & set(types.__all__)
