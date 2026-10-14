# Changelog

Notable changes to `meterflow` (PyPI). Dates are the day the version was cut; what is published is
in [the project roadmap](https://github.com/Donovantxy/MeterFlow/blob/main/docs/ROADMAP.md#where-we-are-2026-10-07).

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
