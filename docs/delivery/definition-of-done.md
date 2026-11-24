# Vertical-Slice Definition of Done

| Field | Value |
|---|---|
| Source | Addendum §P (ADD-P-01…04), CR-017 |
| Related | Governance Handbook v1.0 SOP-007 (requirements traceability), SOP-009 (design), §13.1 (change control) |
| Status | Draft, pending CR-017 approval |

A module is **Done** only when every item below is ticked *and* evidence is linked. A frontend page or a set of
endpoints by itself doesn't count as done (§P).

## The 14 elements

| # | Element | What "done" means | Evidence to link |
|---|---|---|---|
| 1 | Requirements mapping | Every `ADD-*` row and LLD item for the module is listed and has an owner | Traceability matrix rows, issue/PR links |
| 2 | Database migrations | Alembic migrations apply and roll back cleanly; tenant tables have `tenant_id`, RLS ENABLE + FORCE and composite tenant FKs (LLD §4) | Migration files, CI migration job |
| 3 | Backend business logic | Service layer implements the LLD behaviour; no business logic in routers or adapters | Code, review |
| 4 | API endpoints | Versioned `/v1/*` endpoints matching the LLD contract; idempotency keys on commands | OpenAPI diff |
| 5 | Frontend screens | The Next.js screens needed to use the feature end to end, including empty, error and loading states | Screenshots or recording |
| 6 | Authentication and authorization | Actor is authenticated; tenant comes from verified membership, never from the client; RBAC/ABAC; deny by default | Authz tests |
| 7 | Tenant isolation | Cross-tenant read, write, join, job, export and signed-URL tests fail as they should | Isolation test report |
| 8 | Security validation | Input validation, no secrets or PHI in logs, SAST/SCA/secret scan clean, threat notes for new surfaces | CI security job, threat notes |
| 9 | Unit tests | Business logic covered; pure functions and state machines fully covered | Coverage report |
| 10 | Integration tests | Real PostgreSQL/Redis (Docker); provider adapters against mocks and, where available, sandbox | CI integration job |
| 11 | API documentation | OpenAPI descriptions, examples and error codes published | Generated docs |
| 12 | Monitoring and audit events | Metrics, traces (CR-014 span model) and audit events emitted; no PHI in labels | Dashboard or trace screenshot |
| 13 | Acceptance criteria | The module's gates in the [status register](implementation-status-register.md) pass | Test IDs and results |
| 14 | Demonstrable functionality | Live demo on staging with synthetic data only | Recording, staging URL |

## Rules

1. **Gate before dependents.** A module whose hard dependencies aren't Done can't move past *Design*
   (see the [dependency graph](module-dependency-graph.md)). A soft dependency allows the work to start, but its feature stays off until the dependency is Done.
2. **No claims without evidence.** Latency, compliance, production readiness and provider capability claims need linked evidence (R-13, R-14, C-03).
3. **Synthetic data only.** No real PHI or real customer recordings in development, CI or demos (R-10).
4. **Baseline changes go through a CR.** If a slice needs something the LLD doesn't define, raise a CR and wait for approval (Handbook §13.1).
5. **Status values:** Not started → Design → In progress → Gate review → Done. A slice can also be Blocked, and the register must say on what.
