# meterflow

[![license](https://img.shields.io/badge/license-MIT-blue)](./LICENSE)
[![python](https://img.shields.io/badge/python-%E2%89%A5%203.10-blue)](https://www.python.org)

Official Python SDK for [MeterFlow](https://meter-flow.com) — usage-based billing, credit management, and metering.

Track what your customers use, enforce credit balances, gate features, and manage subscriptions with a few lines of code. Fully typed, sync **and** async, one dependency (`httpx`).

---

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Sync or async — same SDK](#sync-or-async--same-sdk)
- [Authentication](#authentication)
- [Core concepts](#core-concepts)
- [Configuration](#configuration)
- [Usage guide](#usage-guide)
  - [Credits](#credits)
  - [Usage events](#usage-events)
  - [Subscriptions](#subscriptions)
  - [Plans](#plans)
  - [Entitlements — ask before you act](#entitlements--ask-before-you-act)
- [Idempotency — safe retries for writes](#idempotency--safe-retries-for-writes)
- [Automatic retries](#automatic-retries)
- [Error handling](#error-handling)
- [Verifying webhooks](#verifying-webhooks)
- [Typing notes](#typing-notes)
- [Versioning & support](#versioning--support)

---

## Requirements

- **Python ≥ 3.10**
- An API key from your [MeterFlow dashboard](https://meter-flow.com) (Project → API Keys)

## Installation

```bash
pip install meterflow
```

The only runtime dependency is [`httpx`](https://www.python-httpx.org). The package ships a `py.typed` marker — mypy and pyright see every field.

## Quick start

```python
import os
from meterflow import MeterFlow

client = MeterFlow(api_key=os.environ["METERFLOW_API_KEY"])

# 1. Grant credits to a customer
client.credits.grant({
    "customer_external_id": "customer_123",
    "amount": 5000,
    "description": "Starter plan — monthly credit grant",
    "metadata": {},
})

# 2. Report what happened, wherever your product does the billable thing
client.usage.record({
    "event_name": "images.generated",
    "customer_external_id": "customer_123",
    "value": 1,
    "properties": {},
})

# 3. Check what they have left
balance = client.credits.balance("customer_123")
print(balance["balance"])  # "4999.000000"
```

That's the whole integration loop: grant → record → check. Everything else in this guide is detail.

## Sync or async — same SDK

Two clients, one surface: every method of `MeterFlow` exists on `AsyncMeterFlow` with the same name, arguments and return shape — the only difference is `await`.

```python
from meterflow import AsyncMeterFlow

async with AsyncMeterFlow(api_key="mf_test_...") as client:
    gate = await client.entitlements.check("customer_123", "images.generated")
```

Both clients hold an `httpx` connection pool: use them as context managers (`with` / `async with`) or call `close()` / `aclose()` when you are done. Create one per process (or per project) and reuse it.

## Authentication

Every request authenticates with the API key you pass to the constructor:

| Key prefix | Environment | Use for |
|---|---|---|
| `mf_live_…` | Live | Real customers, real balances |
| `mf_test_…` | Test | Development, CI, experiments |

The key's environment is a **real data boundary, not a label**: inside the same project, `mf_test_` keys read and write a fully separate dataset from `mf_live_` keys — subscriptions, credits, and usage events created with a test key are invisible to live keys (and vice versa), while your meters and plans are shared, so tests always run against your real billing configuration. The same customer id can hold an independent balance and subscription in each environment, and idempotency keys are namespaced per environment. Point your staging/CI at a test key and production at a live key — same project, zero risk of cross-contamination.

Keys are created in the dashboard (Project → API Keys) and **shown once** at creation — MeterFlow stores only a fingerprint. If a key leaks, revoke it in the dashboard and mint a new one; revocation is immediate.

A key belongs to **one project** and can only see that project's data.

```python
client = MeterFlow(api_key="mf_test_...")  # raises ValueError immediately if the prefix is neither mf_live_ nor mf_test_
```

> Treat API keys like passwords: read them from environment variables or a secret manager, never commit them.

## Core concepts

Four words explain the whole product:

| Concept | What it is | Example |
|---|---|---|
| **Meter** | One countable thing, identified by its `event_name` | `images.generated`, `minutes.transcribed` |
| **Plan** | What you sell: price, billing period, how much of each meter is included, and which on/off features | Starter — $29/month, 5,000 images, `sso` |
| **Subscription** | One customer on one plan from a date; renews itself | `customer_123` → Starter |
| **Credits** | The customer's balance — granted up, spent down, never edited in place | `+5000` granted, `−1340` consumed |

Meters and plans are defined in the dashboard. Your app, through this SDK, does the day-to-day work: creates subscriptions, grants/deducts credits, records usage events (each event lands on the meter whose `event_name` matches), and asks whether a customer may use a feature.

## Configuration

```python
client = MeterFlow(
    api_key="mf_live_...",                          # required — mf_live_* or mf_test_*
    base_url="https://api.meter-flow.com/api/v1",   # optional — override for self-hosted / local dev
    timeout=30.0,                                   # optional — per-request timeout in seconds (default 30)
    retries=3,                                      # optional — automatic retries (default 3, 0 disables)
    transport=None,                                 # optional — an httpx transport (tests, proxies)
)
```

`base_url` is for pointing at a **different MeterFlow server** — a self-hosted deployment, or a locally running stack if you develop MeterFlow itself (`base_url="http://localhost:8000/api/v1"`). If you use the hosted service, leave it at the default; to test your integration safely, use an `mf_test_` key instead (see [Authentication](#authentication)) — no URL change needed.

All configuration lives on the client instance (`client.options`) — there is no global state, no environment-variable sniffing, so you can create multiple clients (e.g. one per project) in the same process.

## Usage guide

### Credits

Credits are an append-only ledger: every grant and deduction is a permanent transaction, and the balance is the sum. Nothing is ever edited in place — which is why a customer's history is always auditable.

**Grant** — add credits (plan renewals, top-ups, goodwill):

```python
txn = client.credits.grant({
    "customer_external_id": "customer_123",
    "amount": 5000,
    "description": "Monthly plan grant",
    "metadata": {},
})
print(txn["balance_after"])  # "5000.000000"
```

**Deduct** — remove credits. Raises `InsufficientCreditsError` (HTTP 402) if the balance can't cover it — the customer is never taken below zero:

```python
from meterflow import InsufficientCreditsError

try:
    client.credits.deduct({
        "customer_external_id": "customer_123",
        "amount": 25,
        "description": "images.generated ×25",
        "metadata": {},
    })
except InsufficientCreditsError:
    ...  # Show your "out of credits — top up" screen. This is an upgrade prompt, not an error page.
```

**Balance** — the current position:

```python
bal = client.credits.balance("customer_123")
bal["balance"]         # "3545.000000"  ← decimal string, see note below
bal["total_granted"]   # "5250.000000"
bal["total_consumed"]  # "1705.000000"
```

**Transactions** — the full history, newest first:

```python
for t in client.credits.transactions("customer_123"):
    print(t["transaction_type"], t["amount"], t["balance_after"], t["description"], t["created_at"])
```

> **Amounts are decimal strings.** Balances and amounts come back as strings (`"3545.000000"`) to avoid floating-point drift on money-like values. Parse deliberately (`decimal.Decimal(...)`) when you need arithmetic. When *sending* an amount, a number or a numeric string are both accepted.

### Usage events

Record an event every time a customer does the thing you charge for. Events are matched to a meter by `event_name` and processed asynchronously into totals (and, if the meter is metered on a plan, into credit deductions).

**Record one event:**

```python
client.usage.record({
    "event_name": "images.generated",
    "customer_external_id": "customer_123",
    "value": 1,                                   # what the meter aggregates: 1 for counts, seconds/MB/etc. for sums
    "properties": {},                             # free-form context; {} when unused
    "timestamp": "2026-09-30T10:00:00Z",          # optional — defaults to arrival time on the server
})
```

**Record a batch** — for high-throughput paths, flush events in groups instead of one request each:

```python
client.usage.record_batch([
    {"event_name": "images.generated", "customer_external_id": "customer_123", "value": 1, "properties": {}},
    {"event_name": "video.seconds_rendered", "customer_external_id": "customer_123", "value": 42, "properties": {}},
])
```

A batch holds at most **500 events** (exported as `MAX_BATCH_EVENTS`). A larger list is rejected locally with `PayloadTooLargeError` before anything is sent — the SDK deliberately does **not** split it for you, because one call is one request with one idempotency key, and turning it into several would make a partial failure indistinguishable from success. Chunk at the call site and give each chunk its own key:

```python
from meterflow import MAX_BATCH_EVENTS

for start in range(0, len(events), MAX_BATCH_EVENTS):
    chunk = events[start : start + MAX_BATCH_EVENTS]
    client.usage.record_batch(chunk, idempotency_key=f"job-42:chunk-{start // MAX_BATCH_EVENTS}")
```

**Summary** — a customer's usage, broken down by meter:

```python
summary = client.usage.summary(
    "customer_123",
    # meter_id="…",                  # optional — narrow to one meter
    from_="2026-09-01T00:00:00Z",    # optional — note the trailing underscore
    to="2026-09-30T23:59:59Z",       # optional
)
for m in summary["meters"]:
    print(m)  # per-meter aggregation and event counts
```

> The `from_` filter has a trailing underscore — it mirrors the API's query parameter exactly (and `from` is a Python keyword anyway).

Recording an event returns immediately (`"processed": False`); totals and any credit deductions materialise moments later. Don't read a balance in the same millisecond and expect the event to be reflected.

### Subscriptions

A subscription puts one customer on one plan and renews itself. Typically your app creates it in the signup flow:

```python
# Pick a plan (defined in the dashboard)…
plans = client.plans.list()
starter = next(p for p in plans if p["slug"] == "starter")

# …and put the new customer on it
sub = client.subscriptions.create({
    "plan_id": starter["id"],
    "customer_external_id": "customer_123",
    "metadata": {},
})
print(sub["status"])  # "trialing" if the plan has trial days, else "active"
```

**List / get:**

```python
everyone = client.subscriptions.list()                          # whole project (in your key's environment)
theirs = client.subscriptions.list(customer_id="customer_123")  # one customer
one = client.subscriptions.get(sub["id"])
```

> Like all reads, these are scoped to the key's environment: a live key lists live subscriptions only, a test key test ones only.

**Update** — change status or metadata. Statuses: `active`, `trialing`, `past_due`, `paused`, `canceled`, `expired`:

```python
client.subscriptions.update(sub["id"], {"status": "paused"})
client.subscriptions.update(sub["id"], {"status": "active"})  # reactivate
```

**Cancel vs delete** — two different operations:

```python
client.subscriptions.update(sub["id"], {"status": "canceled"})  # cancel: the record stays for history
client.subscriptions.delete(sub["id"])                           # delete: removes the subscription record entirely
```

Prefer cancelling: it preserves the subscription's history (a canceled subscription can't be reactivated). Reach for `delete` only when you truly want the record gone — e.g. cleaning up test data.

### Plans

Plans are **read-only** through the SDK — pricing is managed by humans in the dashboard, so a leaked API key can never rewrite your prices.

```python
plans = client.plans.list()          # the project's plans
plan = client.plans.get(plan_id)     # one plan, including its per-meter limits and feature keys
plan["price"]           # "29.00" — decimal string
plan["billing_period"]  # "monthly" | "yearly" | "weekly" | "one_time"
plan["meter_limits"]    # included units + overage rate per meter
plan["features"]        # ["sso", "priority-support"] — the on/off keys check() answers yes to
```

Typical use: render your pricing page or signup flow from `plans.list()` so it can never drift from what billing actually enforces.

### Entitlements — ask before you act

The one call to make **before** doing work for a customer: "may they use this feature — and how much is left?" A **hard** limit says no here; recording usage afterwards never blocks, so an app that skips this call gets an honest ledger but no enforcement.

```python
gate = client.entitlements.check("customer_123", "images.generated")

if not gate["allowed"]:
    # gate["reason"]: "hard_limit_reached" | "no_subscription" | "not_in_plan" | "insufficient_credits"
    return show_upgrade_prompt(gate)  # gate["used"] / gate["included"] / gate["period_end"] are there for the copy

generate_image()
client.usage.record({"event_name": "images.generated", "customer_external_id": "customer_123", "value": 1, "properties": {}})
```

- `feature` is a meter's `event_name` (metered — `included`, `used`, `remaining` filled in) or a plan feature key like `"sso"` (boolean).
- `quantity=5` asks "may they do **5** more?" — one call instead of one per item for batch work.
- A **soft** limit answers `allowed: True` with `reason: "soft_limit_exceeded"` — let it through, nudge the upgrade.
- A **metered** limit stays allowed while the customer's credits cover the overage; otherwise `insufficient_credits`.
- `allowed: False` is a normal returned answer, never an exception. A feature key the project does not know at all is a `NotFoundError` — that is a typo, not a plan.
- The answer carries `Cache-Control: private, max-age=15`; on hot paths cache it per customer for a few seconds rather than calling on every request.

**All of them at once** — for a settings or pricing screen:

```python
result = client.entitlements.get("customer_123")
result["entitlements"]
# [{"feature": "sso", "feature_type": "boolean", "allowed": True, ...},
#  {"feature": "images.generated", "feature_type": "metered", "used": "120", "included": 500, "remaining": "380", ...}]
```

Prefer to be told rather than to ask? Subscribe a webhook to `limit.reached` (see below).

## Idempotency — safe retries for writes

Connections drop. When your app can't tell whether a write arrived, the correct move is to send it again **with the same idempotency key** — MeterFlow recognises the key and acts only once:

```python
client.credits.deduct(
    {"customer_external_id": "customer_123", "amount": 1, "description": "ticket A7", "metadata": {}},
    idempotency_key="deduct-ticket-A7",  # forwarded as the Idempotency-Key header
)
# Sending this twice deducts exactly once and returns the same transaction both times.
```

Every write method accepts the keyword: `credits.grant/deduct`, `usage.record/record_batch`, `subscriptions.create/update`. Use a key that identifies the *business operation* (order ID, job ID) — not a random value per attempt, which would defeat the purpose.

## Automatic retries

The SDK retries transient failures for you — exponential backoff with jitter, 3 attempts by default:

| Situation | Behaviour |
|---|---|
| Network error / connection dropped / timeout | Retried |
| `5xx` server errors | Retried |
| `429 Too Many Requests` | Waits for the server's `Retry-After`, then retries |
| Any other `4xx` (auth, validation, not-found, insufficient credits…) | **Never retried** — it would fail identically |

Configure with `retries=` in the constructor (`0` disables). Combine retries with idempotency keys on writes and a flaky network costs you nothing: the SDK re-sends, the server deduplicates. If a transport failure survives every retry, the underlying `httpx` exception (`httpx.ConnectError`, `httpx.ReadTimeout`, …) is raised as-is.

## Error handling

Every non-2xx response is raised as a typed exception. All of them extend `MeterFlowError`:

| Class | HTTP | `error_type` | Retried by the SDK |
|---|---|---|---|
| `AuthError` | 401 / 403 | `auth_error` | no |
| `InsufficientCreditsError` | 402 | `insufficient_credits` | no |
| `NotFoundError` | 404 | `not_found` | no |
| `ConflictError` | 409 | `conflict` | no |
| `PayloadTooLargeError` | 413 | `payload_too_large` | no — split the batch (see `MAX_BATCH_EVENTS`) |
| `ValidationError` | 422 | `validation_error` | no — per-field detail in `.fields` |
| `RateLimitError` | 429 | `rate_limit` | yes (honours `Retry-After`, exposed as `.retry_after`) |
| `ServerError` | 5xx | `server_error` | yes |

Every error carries:

- **`request_id`** — the API's `X-Request-ID` for that call. Include it when contacting support; it pinpoints the exact request in our logs.
- **`status_code`**, **`error_type`**, and **`retryable`** — for programmatic handling and structured logging.
- **`message`** (also `str(err)`) — the API's own sentence (e.g. `Plan limit reached: the Drip plan includes 5,000 usage events per month…`). A `ValidationError` appends its field detail (`Validation failed: amount: must be greater than 0`) and also exposes it structured as **`.fields`** (`[{"field": ..., "message": ...}]`).

```python
from meterflow import MeterFlowError, InsufficientCreditsError, RateLimitError

try:
    client.credits.deduct({"customer_external_id": "c1", "amount": 999, "metadata": {}})
except InsufficientCreditsError:
    ...  # expected business outcome — prompt a top-up
except RateLimitError as err:
    log.warning("rate limited; server asked to wait %ss", err.retry_after)  # only seen if retries are exhausted/disabled
except MeterFlowError as err:
    log.error("MeterFlow error [%s] status=%s request_id=%s", err.error_type, err.status_code, err.request_id)
    raise
```

## Verifying webhooks

MeterFlow notifies your app of activity you'd otherwise poll for — credits granted or deducted, usage recorded, subscriptions created or updated, a customer reaching a plan limit. Every delivery is signed with **HMAC-SHA256** in the `X-MeterFlow-Signature` header, using the webhook's secret — verify before trusting:

```python
# FastAPI shown; the same three lines work in Flask, Django, or a bare WSGI handler.
from fastapi import FastAPI, Header, HTTPException, Request
from meterflow import verify_webhook

app = FastAPI()

@app.post("/meterflow-webhook")
async def meterflow_webhook(request: Request, x_meterflow_signature: str = Header("")):
    raw_body = await request.body()  # the signature covers the RAW bytes — read them before any JSON parsing

    if not verify_webhook(raw_body, x_meterflow_signature, os.environ["METERFLOW_WEBHOOK_SECRET"]):
        raise HTTPException(status_code=401, detail="invalid signature")  # forged or corrupted — discard

    event = json.loads(raw_body)
    ...  # handle the event
    return {"ok": True}
```

Details that matter:

- **Verify the raw bytes.** If you parse the JSON first and re-serialise, key ordering/whitespace change and the signature won't match.
- The comparison is **timing-safe** (`hmac.compare_digest`) and returns `False` on any mismatch — it never raises on bad input.
- The verifier is pure standard library (`hmac`, `hashlib`) — no network, no client needed; it is also importable as `meterflow.webhook.verify_webhook`.

### Payload shape & event types

Every delivery is a flat JSON object (`Content-Type: application/json`) with two envelope fields — `event` (the type) and `environment` (`"live"` or `"test"`, matching the mode of the API key that caused the activity) — plus type-specific fields:

| `event` | Fired when | Extra fields |
|---|---|---|
| `usage.recorded` | a usage event is ingested (single or batch) | `customer_id`, `event_name`, `value`, `event_id` |
| `credit.granted` | credits are granted | `customer_id`, `amount`, `balance_after`, `transaction_id` |
| `credit.deducted` | credits are deducted | `customer_id`, `amount`, `balance_after`, `transaction_id` |
| `subscription.created` | a subscription is created | `customer_id`, `plan_id`, `subscription_id`, `status` |
| `subscription.updated` | a subscription is updated | `customer_id`, `subscription_id`, `status` |
| `limit.reached` | a customer first reaches a **hard** or **soft** limit's included units this billing period (once per meter per period; metered limits report through `credit.deducted` instead) | `customer_id`, `subscription_id`, `feature` (the meter's `event_name`), `meter_id`, `limit_type`, `included`, `used`, `period_start`, `period_end` |

For example, a `credit.granted` delivery:

```json
{
  "event": "credit.granted",
  "environment": "live",
  "customer_id": "cust_123",
  "amount": 500.0,
  "balance_after": 1250.0,
  "transaction_id": "9b2f6c1e-…"
}
```

When registering a webhook you pick which of these event types it should receive. Deliveries are retried with backoff on non-2xx responses — respond `200` quickly and do the heavy work asynchronously.

Webhooks are registered per-project in the dashboard, which is also where you'll find the secret and each delivery attempt's status.

## Typing notes

- All request/response shapes are **generated from MeterFlow's OpenAPI contract** as `TypedDict`s in `meterflow.types` (`CreditGrantRequest`, `EntitlementResponse`, `PlanResponse`, …). Responses are plain dicts at runtime — no model classes to learn, nothing to serialise — and mypy/pyright check every key you read or write.
- Request fields are `snake_case`, matching the HTTP API one-to-one (`customer_external_id`, not `customerExternalId`). What you see in the docs and dashboard is exactly what you type.
- `properties` (usage events) and `metadata` (credits/subscriptions) default to `{}` on the server; pass `{}` explicitly if your type checker asks for it.
- Public exports: `MeterFlow`, `AsyncMeterFlow`, the error classes, `MAX_BATCH_EVENTS` and `verify_webhook` from `meterflow`; the shapes from `meterflow.types`.

## Versioning & support

- Semantic versioning on the `0.x` line: breaking changes bump the minor, fixes bump the patch.
- Tested in CI on Python **3.10, 3.11, 3.12 and 3.13**.
- The Node.js SDK ([`meterflow` on npm](https://www.npmjs.com/package/meterflow)) exposes the same resources, method names (camelCase there, snake_case here) and error hierarchy — switching languages costs nothing but syntax.
- Issues and source: [github.com/meterflowio/meterflow-python](https://github.com/meterflowio/meterflow-python). Include the `request_id` from any `MeterFlowError` when reporting API issues.

## License

MIT

## The full loop, end to end

```python
import os
from meterflow import MeterFlow

with MeterFlow(api_key=os.environ["METERFLOW_API_KEY"]) as client:
    # Signup: put the customer on a plan and give them their credits
    starter = client.plans.list()[0]
    client.subscriptions.create({"plan_id": starter["id"], "customer_external_id": "ana", "metadata": {}})
    client.credits.grant(
        {"customer_external_id": "ana", "amount": 5000, "description": "Starter grant", "metadata": {}},
        idempotency_key="signup-ana-2026-09",
    )

    # Before every billable action: may she?
    if client.entitlements.check("ana", "images.generated")["allowed"]:
        # …do the work, then report it
        client.usage.record({
            "event_name": "images.generated",
            "customer_external_id": "ana",
            "value": 1,
            "properties": {"model": "sdxl", "resolution": "1024x1024"},
        })

    # Support asks: "what's Ana's situation?"
    balance = client.credits.balance("ana")
    history = client.credits.transactions("ana")
    usage = client.usage.summary("ana")
    entitlements = client.entitlements.get("ana")
```
