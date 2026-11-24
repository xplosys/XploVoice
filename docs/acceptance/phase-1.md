# Phase 1 acceptance report: platform foundation

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Scope: M01 identity, M02 tenants, M17 audit and tenant administration (core), M18 health and metrics, web shell.
Data used: synthetic only. No PHI. This report does not claim production readiness.

## Definition of done (master prompt §31)

| Criterion | Evidence |
|---|---|
| Requirements implemented | [Module register](../module-register.md) traceability table |
| Database migrations work | `alembic upgrade head`, `downgrade base`, `upgrade head` run in CI |
| APIs function | 33 API tests through the HTTP layer (`apps/api/tests`) |
| UI works where applicable | Browser run: register, invite, invitee joins, role-limited views, settings validation, sign-out redirect, sign-in with return path, MFA enrollment, admin denial |
| Authorization enforced | Server-side RBAC on every route; UI hides only what the API already refuses; `test_viewer_cannot_manage_and_denial_is_audited` |
| Tenant isolation verified | `tests/test_isolation.py` (forced RLS on all tenant tables, runtime role, IDOR, body tenant id ignored, cross-user session revoke blocked) |
| Errors handled | Uniform `{code, message}` errors; validation messages shown in forms |
| Audit events generated | Sign-up, sign-in (success/failure), MFA, password, role and member changes, invitations, denials, admin actions |
| Automated tests pass | 33 passed; ruff clean; web typecheck, lint and build pass |
| Documentation updated | This folder |
| Acceptance demonstrated | Browser run above; CI on the pull request |

## Not done in Phase 1 (by design)

- Email delivery (verification, invitations): awaiting configuration of an email provider.
- Single sign-on (OIDC/SAML) for enterprise tenants: planned with Phase 9 hardening.
- Asymmetric JWT keys and secrets-manager integration: Phase 9.
- Docker images were not built in the development sandbox (no Docker daemon); CI builds and scans them.
