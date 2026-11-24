# ADR-0002: Tenant isolation with forced PostgreSQL row-level security

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys · Status: accepted

**Context.** LLD v1.3 §4 requires database-enforced isolation, not only application filters.

**Decision.**
- Every tenant-owned table has `ENABLE` and `FORCE ROW LEVEL SECURITY`, with policies on `app_tenant_id()`.
- Tenant, user and platform-admin context are set per transaction with `set_config(..., true)`, so pooled
  connections never carry context between requests.
- Three roles: `xplovoice_owner` runs migrations; `xplovoice_app` (NOSUPERUSER, NOBYPASSRLS) runs the API;
  `xplovoice_definer` (NOLOGIN, BYPASSRLS) owns only the narrow `SECURITY DEFINER` functions that must work before a
  tenant context exists or across tenants for the caller only. Those functions have a fixed `search_path`,
  column-limited grants, and return only ids.
- Child tables use composite `(tenant_id, id)` foreign keys so a row can never reference another tenant's row.

**Consequences.** A missing `WHERE tenant_id` returns nothing instead of leaking. Every new table must add RLS; the test
`test_every_tenant_table_has_forced_rls` fails if one is missed.
