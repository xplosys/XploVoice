# Phase 6 acceptance report: telephony

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Scope: M04 carriers, trunks and numbers; M06 inbound routing and queues; M07 outbound campaigns and the policy
engine; M22-core consent and do-not-call; the 15-state call lifecycle; transfer, keypad tones and recording consent
in the engine; web screens for each.

Data used is synthetic only, with no PHI. This report does not claim production readiness.

## Exit gates (Phase 0 roadmap)

| Gate | Evidence |
|---|---|
| Real PSTN inbound and outbound in India and the US | **Not shown yet.** Needs a carrier trunk (the customer's, or a contracted one: awaiting configuration) and a LiveKit server with SIP. The SIP path is covered by adapter tests against a mock LiveKit API (`test_livekit_sip_adapter_requests`) and the routing webhook (`test_livekit_webhook_routes_sip_callers_and_ends_calls`) |
| Duplicate-webhook test | `test_carrier_webhooks_are_verified_deduplicated_and_order_tolerant` (same event twice, late event after the end, bad and replayed signatures); `test_livekit_webhook_routes_sip_callers_and_ends_calls` (retried join routes once) |
| Consent and suppression block test | `test_consent_and_do_not_call_block_before_any_carrier_request`: no consent, do-not-call and a disallowed country are blocked and never reach the carrier; `test_opt_out_on_a_call_stops_every_campaign` |
| Toll-fraud caps | `test_toll_fraud_caps`: premium-rate number, country, organisation and platform kill switches, organisation and campaign concurrency, daily minutes; transfers checked too (`test_transfer_success_failure_and_destination_rules`) |

## Definition of done (master prompt §29)

| Criterion | Evidence |
|---|---|
| Migrations | `0006_telephony` upgrades, downgrades to 0005 and upgrades again |
| Automated tests | 166 pass, 28 of them new (21 API, 7 engine); ruff, web typecheck, lint and build are clean |
| Authorization | New permissions: telephony read/manage, campaigns read/manage/approve, consent read/manage, mapped to the five roles (`test_roles_for_telephony`, `test_campaigns_need_approval_by_another_person`) |
| Tenant isolation | FORCE RLS and composite tenant keys on all 15 new tables; carrier lookups through definer functions that return ids only; `test_inbound_calls_stay_in_their_organisation`, `test_new_tables_force_rls_and_histories_are_append_only` |
| Audit | Trunks, numbers, routes, queues, policy changes and the kill switch, campaign create/approve/start/pause/cancel, contact imports, consent and do-not-call changes; every policy decision with its checks |
| Reliability | Idempotent, order-tolerant carrier events; dialer safe in several processes (`SKIP LOCKED`); queue timeouts; failed transfer returns to the agent |
| Documentation | ADR-0009, module register, CR-003, CR-005, CR-009, CR-011 updated, test cases `phase-6-test-cases.md`, local development guide |

## Browser walkthrough

Checked in Chromium at Asia/Kolkata time: add a simulated trunk (password hidden), add a number, route it to a
published agent, ring it (call routed, then ended by a carrier event, with its lifecycle and carrier events shown),
add a number to the do-not-call list, create a campaign, import three contacts and one bad row with consent,
approve and start it. At 00:18 IST the two consented contacts were deferred to 09:03 IST (India window), and the
listed number was blocked, with every check shown.

## Not done in Phase 6 (later phases or awaiting configuration)

- Real PSTN calls: need a carrier trunk and LiveKit SIP. Numbers bought from XploVoice need a carrier contract.
- Call recording storage (egress, storage, retention): awaiting configuration. The notice and consent work.
- Warm transfer, hold music, national do-not-call registry lookups.
- Legal review of calling windows and consent rules (TRAI/TCCCPR, TCPA/DNC) is still open; the defaults are not
  legal advice.
- Telephony prices and charging: Phase 7.
