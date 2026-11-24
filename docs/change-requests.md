# Change request log

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Raised in the Phase 0 architecture validation report under Governance Handbook §13.1. "Accepted" means Xplosys
approved the build to proceed on the proposal; the formal baseline document still needs updating.

## Conflicts between documents

| ID | Conflict | Resolution in use |
|---|---|---|
| X-1 | LLD v1.3 refers to M01–M18 but no document defines them | Provisional IDs (CR-001) |
| X-2 | M22 depends on M07, but outbound needs consent first | Split M22-core (before M07) and M22-outbound (CR-023) |
| X-3 | HLD v1.0: Hindi + Indian English; master prompt adds Hinglish | Hinglish as its own language profile (CR-016) |
| X-4 | HLD v1.0 puts inbound PSTN in Phase 2; master prompt in Phase 6 | Master prompt order; carrier onboarding starts early |
| X-5 | HLD v1.0 has 7 agent states; master prompt has 5 | 5 states; "configured" and "active" become flags (CR-006) |

## Change requests

| CR | Missing specification | Modules | Priority | Status |
|---|---|---|---|---|
| CR-001 | Core LLD for M01–M18 | M01–M18 | Blocker | Accepted (provisional IDs); M01, M02, M17, M18 slices implemented |
| CR-002 | Common engine + channel adapter contract, incl. browser WebRTC | M09, M10 | High | Open |
| CR-003 | 15-state call lifecycle, idempotent order-tolerant events | M04, M08 | High | Open |
| CR-004 | Latency instrumentation and benchmark workload | M10, M18 | High | Open |
| CR-005 | Carrier adapters, capability registry, trunks, DIDs, destination policies | M04 | High | Open |
| CR-006 | Agent version schema; 5-state lifecycle | M05 | High | Open |
| CR-007 | Tool gateway and RAG authorization | M09, M12 | High | Open |
| CR-008 | Native workflows: follow-ups, holiday calendars, support tickets | M11, M13, M14 | Medium | Open |
| CR-009 | Inbound routing + queues; outbound policy engine, suppression, dial attempts | M06, M07 | High | Open |
| CR-010 | Worker and queue spec: heartbeats, DLQ, backpressure, regional routing | M10 | High | Open |
| CR-011 | Consent, retention, recording audit for standard tenants | M22, M24 | Medium | Open |
| CR-012 | Platform-wide fallback chains and circuit breakers | M03, M04, M09 | High | Open |
| CR-013 | Concurrency, capacity and admission control | M10, M15 | High | Open |
| CR-014 | Per-call trace span model and monitoring catalogue | M18, M16 | Medium | Open |
| CR-015 | Core acceptance test catalogue (VX-xxx) | All | High | Open |
| CR-016 | Hinglish and country/language registry | M02, M03 | Medium | Partial: registry in `m02_tenant/regional.py` lists `hi-Latn-IN` |
| CR-017 | Vertical-slice definition of done, dependency graph, status register | All | High | Partial: [module register](module-register.md) |
| CR-018 | Customer-owned provider credentials | M03 | Medium | Open |
| CR-019 | Ten agent templates | M05 | Low | Open |
| CR-020 | KB malware scanning, document versioning, retrieval audit | M12 | Medium | Open |
| CR-021 | Integration framework (OAuth, sync logs, retries) | M13 | Medium | Open |
| CR-022 | Subscriptions, PAYG, invoices, FX, cost and charge ledgers | M15 | Medium | Open |
| CR-023 | Resolve M07/M22 cycle | M07, M22 | High | Accepted (split) |
| CR-024 | Public marketing site pages | Web | Low | Implemented (content makes no compliance claims) |
| CR-025 | Password change must end sessions in every tenant, not only the current one | M01 | High | Implemented: `revoke_my_sessions` definer function, test `test_password_change_revokes_sessions_in_every_org` |
