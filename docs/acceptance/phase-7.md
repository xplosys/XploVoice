# Phase 7 acceptance report: commercial SaaS

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Scope: M15 plans, prices, subscriptions, rating, quotas, spending limits, invoices and payments (test provider);
M16 analytics; plan limits on agents, numbers and concurrent calls; admin billing console; web screens for each;
the Phase 6 follow-up label "self-approved" on campaigns.

Data used is synthetic only, with no PHI. No real payment was made. This report does not claim production readiness.

## Master prompt §22

| Requirement | Evidence |
|---|---|
| INR and USD, provider currency kept apart from billing currency | `test_phone_minutes_rated_with_included_minutes_then_invoiced_with_tax`, admin overview per currency (`test_admin_assigns_credits_voids_and_sees_cost_next_to_charges`) |
| Subscriptions and pay-as-you-go | `test_plan_activation_needs_a_fee_and_prices_are_append_only`, `test_trial_waives_the_fee_and_ends_into_a_paid_period` |
| Quotas, monthly limits, spending limits, cost alerts | `test_quota_blocks_inbound_and_defers_campaign_calls`, `test_spending_limit_alerts_once_and_hard_limit_blocks_new_calls`, `test_plan_limits_on_agents_numbers_and_concurrent_calls` |
| Invoices and an auditable ledger | `test_phone_minutes_rated_with_included_minutes_then_invoiced_with_tax`, `test_billing_permissions_isolation_and_append_only_ledger` |
| Idempotent billing events | `test_rating_is_idempotent_keeps_the_price_in_force_and_skips_customer_keys`, `test_test_payment_settles_through_the_signed_webhook_once` |
| No single estimated per-minute price | Prices are dated per meter and plan; nothing is seeded (`test_no_plans_or_prices_are_seeded_and_only_platform_admins_write_the_catalog`) |

## Definition of done (master prompt §29)

| Criterion | Evidence |
|---|---|
| Migrations | `0007_billing` upgrades, downgrades to 0006 and upgrades again |
| Automated tests | 185 API tests pass, 19 of them new; ruff, web typecheck, lint and build are clean |
| Authorization | New permissions billing:read (owner, admin) and analytics:read (every role); changing the plan, settings or paying needs billing:manage (owner only); the catalog is platform admin only |
| Tenant isolation | FORCE RLS on all 8 new tenant tables; payment lookup by reference through a definer function that returns ids only; `test_billing_permissions_isolation_and_append_only_ledger` |
| Audit | Plan, price, FX and tax changes, subscriptions, credits, voids, alerts, payments, billing runs |
| Reliability | Rating under an advisory lock with unique source keys; webhooks deduplicated by event id; settled payments never overturned |
| Documentation | ADR-0010, module register, CR-013 and CR-022 updated, test cases `phase-7-test-cases.md`, local development guide |

## Browser walkthrough

Checked in Chromium at Asia/Kolkata time with demo plans entered by a platform admin: the Billing page with the
period's use, included minutes and spending alerts; an open invoice with GST (demo) 18%; a declined test payment,
then a successful one marking the invoice paid; Analytics for the last 7 days; a new organisation put on the
default plan's 14-day trial; and the admin Billing console with charges next to provider cost.

## Not done in Phase 7 (later phases or awaiting configuration)

- A real payment gateway (cards, UPI): awaiting a contract. Only the test provider exists, development only.
- Real prices, tax registration and GST e-invoicing: to be entered by Xplosys; demo values were used for screenshots.
- Credit notes, refunds and proration of mid-period plan changes.
- Exports of analytics and invoices beyond print to PDF.
