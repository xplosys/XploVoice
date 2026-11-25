# Phase 2 acceptance report: AI providers, gateway and metering

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Scope: M03 AI provider registry and gateway, M15 usage metering (first slice), web AI pages, admin AI catalog.
Data used: synthetic only. No PHI. This report does not claim production readiness.

## Definition of done (master prompt §31)

| Criterion | Evidence |
|---|---|
| Requirements implemented | [Module register](../module-register.md), Phase 2 traceability table; [ADR-0005](../adr/0005-ai-gateway-and-metering.md) |
| Database migrations work | `0002_ai_providers` upgrades, downgrades to `0001_foundation` and upgrades again |
| APIs function | 24 new API tests (12 adapter contract, 12 acceptance); 57 in total pass |
| UI works where applicable | Browser run: set LLM/STT/TTS order, playground chat, speech and transcription, usage page, admin AI catalog |
| Authorization enforced | `ai:read`, `ai:manage`, `ai:test`, `usage:read` checked server side; `test_roles_limit_who_configures_and_tests` |
| Tenant isolation verified | FORCE RLS on all new tenant tables (covered by `test_every_tenant_table_has_forced_rls`); `test_other_tenants_keys_and_usage_are_invisible` |
| Errors handled | No route gives a clear 503 listing attempts and skipped providers, never an invented answer |
| Audit events generated | Key add, verify, revoke; route changes; every admin catalog change with its reason |
| Automated tests pass | 57 passed; ruff clean; web typecheck, lint and build pass |
| Documentation updated | Module register, CR log (CR-012, CR-018, CR-022), ADR-0005, `.env.example` |

## Not done in Phase 2 (by design)

- XploVoice-managed vendor accounts, model list and prices: awaiting configuration. Platform admins add them in the
  admin AI catalog from each vendor's current price page.
- Real-time streaming inside a live call (Phase 3); the gateway already streams LLM tokens.
- Charging customers for usage, plans and invoices (Phase 7).
