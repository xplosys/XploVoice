# Phase 4 acceptance report: agent builder

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Scope: M05 agent builder (all master prompt §9 fields), ten templates (§10), immutable versions, testing, publishing,
pause, rollback and archive, with web screens for each.

Data used is synthetic only, with no PHI. This report does not claim production readiness.

## Exit gate (Phase 0 roadmap)

| Gate | Evidence |
|---|---|
| Calls pin version | `test_calls_pin_the_version_they_started_with`: a running call keeps version 1 after version 2 is saved; new calls use the latest; a chosen version is honoured. `test_production_traffic_uses_only_the_published_version` |
| Publish/rollback demo | `test_lifecycle_test_publish_pause_resume`, `test_rollback_only_to_a_previously_published_version`; browser demo screenshots in the project's `demo/phase-4` folder (template, builder, test call, publish, edit, publish, roll back, compare) |
| Template set loads | `test_ten_templates_load_and_create_editable_agents`, `test_templates_are_valid_configs` |

## Definition of done (master prompt §29)

| Criterion | Evidence |
|---|---|
| Migrations | `0004_agent_builder` upgrades, downgrades to 0003 and upgrades again; Phase 3 agents are migrated to draft or testing |
| Automated tests | 116 pass, 33 of them new (27 builder API, 6 engine); ruff, web typecheck, lint and build are clean |
| Authorization | `agents:publish` (owner, admin) for publish, rollback, pause, resume and archiving a live agent; designers build and test; viewers read |
| Tenant isolation | FORCE RLS on agents, versions and publications; IDOR tests on every builder endpoint; templates are read-only platform data |
| Audit | agent created/updated, publish (with skip-test reason), rollback, pause, resume, archive, restore |
| Traceability | Every call records agent version and provider, model and model version per kind (ADD-F-07) |
| Documentation | ADR-0007, module register, CR-006 and CR-019, test cases `phase-4-test-cases.md` |

## Not done in Phase 4 (later phases or awaiting configuration)

- Knowledge base and tool execution: Phase 5. Grants are stored and the readiness checks say they don't run yet.
- Transfer to a phone number, recording and consent capture: Phase 6. Browser calls end with `transfer_requested`.
- Real AI vendors: awaiting configuration. All tests and demos use the development-only mock provider.
