"""Official Python SDK for MeterFlow — usage-based billing, credit management, and metering.

from meterflow import MeterFlow

client = MeterFlow(api_key="mf_live_...")
client.credits.grant({"customer_external_id": "customer_123", "amount": 5000, "metadata": {}})
"""

from ._version import __version__
from .client import AsyncMeterFlow, ClientOptions, MeterFlow
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
from .resources.usage import MAX_BATCH_EVENTS
from .webhook import verify_webhook

__all__ = [
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
]
