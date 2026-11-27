# ADR-0010: Plans, rating, invoices and payments

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys · Status: accepted for development

**Context.** Phase 7 adds commercial billing (M15) and analytics (M16). Master prompt §22 asks for INR and USD,
subscriptions and pay-as-you-go, quotas, monthly limits, cost alerts, spending limits, invoices, an auditable ledger
and usage reports, with provider cost kept apart from tenant charges and idempotent billing events, and says no
single estimated per-minute price is the source of truth. No price list, tax registration or payment gateway has
been agreed, so none is built in.

**Decision.**

**Catalog**
- Plans (`billing_plans`) are monthly subscriptions or pay-as-you-go, in one currency (INR or USD), with optional
  limits (agents, concurrent calls, phone numbers) and trial days. One default plan per currency is given to new
  organisations.
- Prices (`plan_prices`) are append-only and dated (`effective_from`): a change applies from the moment it is added
  and never re-prices past use. Each price is per meter (plan fee, inbound and outbound phone minutes, AI input and
  output per 1,000 tokens, speech-to-text minutes, text-to-speech per 1,000 characters), with an included quantity
  and an optional monthly quota.
- FX rates and tax rates are entered by a platform admin with their source. FX is used only to compare provider
  cost with charges; it never changes what a tenant is charged. Tax applies to invoices issued after it is added;
  without one, invoices say tax is awaiting configuration.
- Nothing is seeded. Only platform admins write the catalog, with a reason, audited.

**Rating**
- Measured use (Phase 2 `usage_events` for managed AI keys, Phase 6 `telephony_usage` in billed seconds) is rated
  into `charge_ledger`, append-only, with a unique `source_key` per source row. Rating runs under a per-organisation
  advisory lock and `on conflict do nothing`, so running it twice charges once.
- The price used is the one in force when the use happened. Use on customer-owned AI keys is never charged.
  Use with no plan price is kept in usage reports but not charged.
- Provider cost stays in the usage ledger in the provider's currency; charges are in the organisation's billing
  currency.

**Admission**
- Before a call, chat, AI request or campaign dial, `billing.admission` checks: overdue invoice (configurable),
  hard spending limit, monthly quota on the meter, and (optionally) no plan. Blocks return 402; inbound calls hang
  up with `billing_<reason>`; campaign calls are deferred 30 minutes.
- Spending alerts at the organisation's chosen percents are sent once per period (event `billing.alert`, audited).

**Invoices and periods**
- At period end: fee for the new period (waived while trialing), pending plan change or cancellation applied,
  invoice issued from the ledger with tax, number `XV-<year>-<sequence>`, and a snapshot of the bill-to details.
  Overdue invoices move the subscription to past due. The job runs in the API every 5 minutes.

**Payments**
- A provider adapter settles invoices through signed, deduplicated webhooks (`payment_events` unique per provider
  event). A settled payment is never overturned; amount or currency mismatch fails the payment.
- Only the test provider exists. It is refused in staging and production, moves no money and signs its own webhook.
  The real gateway is listed as awaiting configuration. Card and UPI details never touch XploVoice.

**Consequences.**
- Prices can change without touching past invoices; audits can trace every charge to its usage row.
- A gateway contract needs one new adapter and webhook route; the ledger and invoices stay as they are.
- Credit notes, refunds, proration on mid-period changes, and e-invoicing (GST IRN) are not built yet.
