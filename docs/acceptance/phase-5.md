# Phase 5 acceptance report: knowledge, workflows, tools and integrations

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Scope: M11 workflows and follow-ups, M12 knowledge base and retrieval, M13 integrations, M14 support tickets and
notifications, tools and retrieval in the conversation engine (addendum G and H), with web screens for each.

Data used is synthetic only, with no PHI. This report does not claim production readiness.

## Exit gates (Phase 0 roadmap)

| Gate | Evidence |
|---|---|
| O6: RAG retrieves only authorized tenant data | `test_retrieval_reads_only_the_agents_own_tenant_and_granted_active_knowledge`: another tenant's text, an ungranted knowledge base and an archived one are never returned; `test_retrieved_text_is_marked_as_data_not_instructions`; FORCE RLS on all 18 new tables (`test_every_tenant_table_has_forced_rls`) |
| O7: Tools execute only with valid permissions | `test_tools_run_only_when_granted_enabled_valid_and_never_twice` (not granted, switched off, invalid input, repeated request), `test_sensitive_actions_wait_for_a_person`, `test_role_permissions_for_phase_5` |

## Definition of done (master prompt §29)

| Criterion | Evidence |
|---|---|
| Migrations | `0005_knowledge_tools` upgrades, downgrades to 0004 and upgrades again |
| Automated tests | 138 pass, 22 of them new; ruff, web typecheck, lint and build are clean |
| Authorization | New permissions: knowledge, workflows, support, notifications, tools (manage, approve) and integrations, mapped to the five roles |
| Tenant isolation | FORCE RLS and composite tenant keys on every new table; cross-tenant ids return 404; the webhook dispatcher reads due rows through a definer function and works under each delivery's tenant |
| Audit | Tool uses (actor "service"), approvals and denials, knowledge, calendar, template and webhook changes |
| Reliability | Tool timeouts, one retry, contained failures (`test_tool_failures_are_contained`); webhook retries with backoff and dead after 8 attempts (`test_dead_after_max_attempts`) |
| Documentation | ADR-0008, module register, CR-020 and CR-021 updated, test cases `phase-5-test-cases.md`, local development guide |

## Browser walkthrough

Screenshots in the project's `demo/phase-5` folder: knowledge base with search, booking calendar, builder grants,
text chat that answers from the knowledge base, books, opens a ticket and asks to cancel (held for approval), the
call record with its actions, approvals, tickets, leads, follow-ups, messages (held, awaiting configuration) and a
webhook (private address refused, secret shown once).

## Not done in Phase 5 (later phases or awaiting configuration)

- Embedding search: needs an embedding vendor (awaiting configuration) and pgvector.
- SMS and email delivery: needs a provider account (awaiting configuration). Messages are kept as held.
- CRM and calendar connectors: need OAuth clients registered with each vendor (awaiting configuration).
- Order lookup: needs an order system connected.
- ClamAV is used when `XV_CLAMAV_URL` is set; production-like environments refuse uploads without it.
- Real AI vendors: awaiting configuration. All tests and demos use the development-only mock provider.
