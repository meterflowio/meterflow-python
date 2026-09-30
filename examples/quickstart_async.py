"""MeterFlow Python SDK — Quickstart (async client).

The same loop as quickstart.py — grant → balance → deduct → record → history → entitlements — on
``AsyncMeterFlow``: identical method names, every call awaited. Run from sdks/python:

  METERFLOW_API_KEY=mf_test_... METERFLOW_BASE_URL=http://127.0.0.1:8000/api/v1 python examples/quickstart_async.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from meterflow import AsyncMeterFlow

CUSTOMER_ID = "quickstart-customer-2"


async def main() -> int:
    api_key = os.environ.get("METERFLOW_API_KEY")
    if not api_key:
        print("Set METERFLOW_API_KEY before running this example.", file=sys.stderr)
        return 1

    async with AsyncMeterFlow(api_key, base_url=os.environ.get("METERFLOW_BASE_URL", "http://localhost:8000/api/v1")) as client:
        print("=== MeterFlow SDK Quickstart (async) ===\n")

        grant = await client.credits.grant(
            {"amount": 500, "customer_external_id": CUSTOMER_ID, "metadata": {}}, idempotency_key=f"qs-grant-{CUSTOMER_ID}-1"
        )
        print(f"1. Granted 500 → balance_after={grant['balance_after']}")

        balance = await client.credits.balance(CUSTOMER_ID)
        print(f"2. Balance={balance['balance']}")

        deduct = await client.credits.deduct(
            {"amount": 100, "customer_external_id": CUSTOMER_ID, "metadata": {}}, idempotency_key=f"qs-deduct-{CUSTOMER_ID}-1"
        )
        print(f"3. Deducted 100 → balance_after={deduct['balance_after']}")

        # Independent calls run concurrently — the point of the async client.
        event, history, entitlements = await asyncio.gather(
            client.usage.record({"event_name": "api_call", "customer_external_id": CUSTOMER_ID, "value": 1, "properties": {}}),
            client.credits.transactions(CUSTOMER_ID),
            client.entitlements.get(CUSTOMER_ID),
        )
        print(f"4. Event recorded id={event['id']}")
        print(f"5. {len(history)} transaction(s)")
        print(f"6. {len(entitlements['entitlements'])} entitlement(s)\n")

    print("=== Quickstart complete ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
