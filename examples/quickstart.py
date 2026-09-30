"""MeterFlow Python SDK — Quickstart (sync client).

A smoke test / demo that exercises every SDK resource against a live local API, in order:

  1 - Grant 500 credits to a test customer (quickstart-customer-1)
  2 - Check balance — confirms the 500 landed
  3 - Deduct 100 credits — verifies write + balance update
  4 - Record a usage event (api_call, value=1)
  5 - List credit transactions
  6 - List plans and this customer's entitlements (empty without a subscription — that is the honest answer)
  7 - Verify a webhook signature — sign a payload with HMAC-SHA256, verify with the right and a wrong secret

Prerequisites (same as the Node quickstart — see sdks/node/examples/quickstart.ts for the curl steps):
  a project, an API key, and a meter named `api_call` on the local stack.

Run (from sdks/python):
  METERFLOW_API_KEY=mf_test_... METERFLOW_BASE_URL=http://127.0.0.1:8000/api/v1 python examples/quickstart.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys

from meterflow import MeterFlow, verify_webhook

CUSTOMER_ID = "quickstart-customer-1"


def main() -> int:
    api_key = os.environ.get("METERFLOW_API_KEY")
    if not api_key:
        print("Set METERFLOW_API_KEY before running this example.", file=sys.stderr)
        return 1

    with MeterFlow(api_key, base_url=os.environ.get("METERFLOW_BASE_URL", "http://localhost:8000/api/v1")) as client:
        print("=== MeterFlow SDK Quickstart (sync) ===\n")

        print("1. Granting 500 credits...")
        grant = client.credits.grant(
            {"amount": 500, "customer_external_id": CUSTOMER_ID, "metadata": {"reason": "quickstart"}},
            idempotency_key=f"qs-grant-{CUSTOMER_ID}-1",
        )
        print(f"   ✓ Granted — tx id={grant['id']}, balance_after={grant['balance_after']}\n")

        print("2. Checking balance...")
        balance = client.credits.balance(CUSTOMER_ID)
        print(f"   ✓ Balance={balance['balance']}\n")

        print("3. Deducting 100 credits...")
        deduct = client.credits.deduct(
            {"amount": 100, "customer_external_id": CUSTOMER_ID, "description": "API call fee", "metadata": {}},
            idempotency_key=f"qs-deduct-{CUSTOMER_ID}-1",
        )
        print(f"   ✓ Deducted — tx id={deduct['id']}, balance_after={deduct['balance_after']}\n")

        print("4. Recording a usage event...")
        event = client.usage.record(
            {"event_name": "api_call", "customer_external_id": CUSTOMER_ID, "value": 1, "properties": {}},
            idempotency_key=f"qs-usage-{CUSTOMER_ID}-1",
        )
        print(f"   ✓ Event recorded — id={event['id']}\n")

        print("5. Listing credit transactions...")
        transactions = client.credits.transactions(CUSTOMER_ID)
        print(f"   ✓ Found {len(transactions)} transaction(s)")
        for tx in transactions:
            print(f"     [{tx['transaction_type']}] amount={tx['amount']} balance_after={tx['balance_after']}")
        print()

        print("6. Plans and entitlements...")
        plans = client.plans.list()
        print(f"   ✓ {len(plans)} plan(s): {', '.join(plan['name'] for plan in plans) or '—'}")
        entitlements = client.entitlements.get(CUSTOMER_ID)
        print(f"   ✓ {len(entitlements['entitlements'])} entitlement(s) for {CUSTOMER_ID} (plan_id={entitlements['plan_id']})\n")

    print("7. Webhook signature verification...")
    secret = "example-webhook-secret"
    payload = json.dumps({"event": "credit.granted", "customer_id": CUSTOMER_ID, "amount": 500})
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    print(f"   ✓ Valid signature:    {verify_webhook(payload, signature, secret)}")
    print(f"   ✓ Tampered signature: {verify_webhook(payload, signature, 'wrong-secret')}\n")

    print("=== Quickstart complete ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
