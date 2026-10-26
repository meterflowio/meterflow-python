# Changelog

Notable changes to `meterflow` (PyPI). Dates are the day the version was cut; what is published is
in [the project roadmap](https://github.com/Donovantxy/MeterFlow/blob/main/docs/ROADMAP.md#where-we-are-2026-10-07).

## Unreleased

**`webhooks.delivery_page(webhook_id, limit=, cursor=)` reads an endpoint's receipts past the newest 100.**
It returns `{"data": [...], "next_cursor": ...}` like `subscriptions.list()`: newest first, scoped
to your key's environment, and `cursor=page["next_cursor"]` reads the page after. The new
`WebhookDeliveryPage` type is exported from `meterflow.types`. `webhooks.deliveries()` is unchanged
and still returns the newest 100 as a list, so nothing you wrote changes.

**`subscriptions.list()` searches and filters by status on the server.** Two new keyword
arguments: `q`, a case-insensitive contains on the customer id (`%` and `_` are matched literally),
and `status`, a list of subscription statuses (`["past_due", "paused"]`), sent as the parameter
repeated. Both apply before the page is cut, so pass them again with `cursor` to read the next page of
the same matches. An unknown status raises `ValidationError`. Nothing you wrote changes; until now
the only filter was the exact `customer_id`, which still works and combines with both.

**`plans.list()`, `plans.get()` and `webhooks.list()` carry two new fields, `created_by` and `created_by_email`, both always `null` for an API-key caller.** They name the dashboard user who created the row, which is for the dashboard's own tables, not for an integration holding a key; they exist on the type so the one response serves both. Nothing you call changes; a test fixture you typed as `PlanResponse` or `WebhookResponse` needs the two fields added to compile.

**A canceled subscription can be reactivated.** `subscriptions.update(id, {"status": "active"})` on a
canceled subscription now succeeds instead of raising the 409: `canceled_at` is cleared, and if the
old period has ended a fresh one starts now — with the plan's price granted in credits and a
`subscription.renewed` webhook whose `reason` is `period_reactivated`. A trial canceled before its end
comes back as `trialing` with the same end date. A plan that is unpublished or switched off since the
cancel raises the 409, as it does for a new subscription. Any other status on a canceled subscription still
raises it, and so does a reactivation of a subscription your payment-provider connector drives —
reactivate it at the provider. The signature is unchanged; code that caught the 409 to mean "gone
for good" should expect the updated subscription back.

**`entitlements.get()` answers each metered row for the next unit**, exactly as `check()` does. A
row can now read `allowed: False` with `reason` `insufficient_credits`, `spend_cap_reached` or
`hard_limit_reached` (and a soft row `soft_limit_exceeded`) where it used to read `allowed: True`
until the line was crossed — a hard limit at exactly its allowance is now refused, because the next
unit would be. `used` and `remaining` are unchanged. Reading the list never fires a webhook; only
`check()` announces `balance.exhausted`. Both reads now also send `Vary: Authorization`, so a browser
never serves one key's answer to another. The signature is unchanged; if you drew "allowed" from the
list, it now agrees with the gate.

**A malformed item in `usage.record_batch()` is a 422, not a 500.** An item that is not an object used
to crash the API's error handler; it now raises `ValidationError` with the item named by its path
(`events.0`). Nothing changes for a well-formed body.

**`usage.summary()` rows carry `aggregation_field`** — the meter's own property name, null on a
count meter. A row's `value` is in a different unit per meter (events on a count meter, the property
on a sum / max / min one, distinct values of it on a unique_count one), so this is what lets you label
it. Additive: nothing you wrote changes.

**`credits.balance()` says whether usage will draw on the balance**: a new `usage_draws_credits`
field. `True` when the customer's active or trialing subscription is on a plan with a metered limit
at a rate (on a meter whose value is a quantity), so recorded usage beyond the allowance is charged
to it; `False` when it has such a subscription and no such limit — not an error: the balance moves
only when your app calls `credits.deduct`; `None` without an active or trialing subscription, when
there is no plan to say anything about. The portal's balance read carries it too. Additive.

**`webhooks.deliveries(id)` no longer returns `next_retry_at`.** It was null on every receipt: a
delivery is tried up to five times with backoff inside the same run, and no later attempt is ever
scheduled, so there was never a time to report. `attempts` still counts the tries. A typed reader
fails mypy on the missing key and an untyped one gets a `KeyError` — drop the read.

**A webhook receipt read during a delivery shows where it stands.** `webhooks.deliveries(id)` now
returns `pending` before the first try and `retrying` between tries, with the live `attempts`,
`response_code` and `response_body`; before, a receipt only ever showed the final `success` or
`failed`. Additive: the four statuses were already in the type, and nothing stops compiling.

**Webhook retries survive a worker restart.** A failed delivery's next try is now scheduled
through the queue after the same delays (30 s, 5 min, 30 min, 2 h) instead of a worker waiting in
place, so a retry waiting in the queue survives a deploy instead of leaving its receipt at
`retrying`. Nothing changes
for a reader of `webhooks.deliveries(id)`: the same statuses, `attempts` and timing.

**An idempotency key is remembered for 24 hours.** A write retried with the same key more than a
day after the original is now a new write, not a replay of the original (and no longer a 409 when
the body differs). Nothing changes for a client that retries promptly; a key you reuse on purpose,
like an order id, identifies one operation per day. A subscription is the one shape that differs: its customer already has one, so a late retry meets the usual one-per-customer 409 rather than a replay.

## 0.3.0 — 2026-10-15

**`portal.create_session()` reads your project's defaults.** `topup_url`, `return_url` and
`expires_in_minutes` are settings on the project now (dashboard → Portal), and a call that leaves
one out uses the project's value rather than nothing. A value you pass still wins. If you relied on
"omitted means no Buy more button", clear the project's checkout address.

**`entitlements.get()` now answers with `plan_name`** beside `plan_id`, null exactly when `plan_id`
is — so a screen showing a customer their plan no longer needs a second read to print its name.

**`portal.create_session()` returns the link that customer already holds.** Called with only
`customer_external_id` while an earlier link is still valid, it gives back **that** link instead of
minting a second one. Naming `topup_url`, `return_url` or `expires_in_minutes` asks for a different
link and replaces it. Same signature, same response shape; only "every call is a fresh link" is no
longer true.

## 0.2.0 — 2026-10-14

**New: `portal.create_session()`** (and `AsyncMeterFlow.portal`) — mint a short-lived link to the
MeterFlow-hosted balance page for one of your customers. The link reads that one customer's balance
and ledger and nothing else; "buy more" goes to your own checkout, and MeterFlow never takes the
payment. The two reads behind the page are deliberately not on this client: they belong to the
person holding the link.

**Breaking: the two lists that grow without a limit now answer a page.**

- `credits.transactions(customer_id)` returns `CreditTransactionPage` —
  `{"data": [...], "next_cursor": ...}` — instead of `list[CreditTransactionResponse]`, and takes
  `limit` and `cursor`.
- `subscriptions.list()` returns `SubscriptionPage` instead of `list[SubscriptionResponse]`, and
  takes `limit` and `cursor` beside `customer_id`.

Both apply to the async clients too. `data` holds the rows, newest first; `next_cursor` is the
opaque mark for the page after this one and is `None` on the last page. Pass it back as `cursor`
unchanged. `limit` is 1–200 and defaults to 50 — a `limit` outside that range, or a cursor this API
did not mint, is a `422`.

**Migrating** — wherever a call was iterated directly:

```diff
-for t in client.credits.transactions("customer_123"):
+for t in client.credits.transactions("customer_123")["data"]:
```

`mypy` finds every one of these: the return type changed. Nothing else in the SDK changed —
`plans.list()`, `webhooks.list()` and the rest stay plain lists, because what they return is
bounded by a plan cap or by configuration.

Why a cursor rather than a page number: [DECISIONS,
2026-10-14](https://github.com/Donovantxy/MeterFlow/blob/main/docs/DECISIONS.md).
