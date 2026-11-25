# Module register

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

M19–M25 are official module IDs from LLD v1.3 §2. M01–M18 are referenced by LLD v1.3 but defined in no supplied
document. They are **provisional** IDs proposed in the Phase 0 report and accepted under CR-001; they will be replaced
if Xplosys supplies the earlier LLD.

Status values: *done* (meets the definition of done for the slice delivered), *partial* (slice delivered, more scope in a
later phase), *planned*, *awaiting configuration* (code path exists but needs a vendor account, key or contract).

| ID | Module | Phase | Status | Delivered in this repository |
|---|---|---|---|---|
| M01 | Identity, authentication, MFA, sessions | 1 | done | `apps/api/xplovoice_api/modules/m01_identity`; email verification sending is awaiting configuration |
| M02 | Tenants, members, invitations, regional settings | 1 | done | `modules/m02_tenant`; invitation email is awaiting configuration (dev returns the link) |
| M03 | AI provider registry and gateway | 2 | done | `modules/m03_ai`: catalog, adapters (OpenAI, Anthropic, Deepgram, ElevenLabs, Sarvam, OpenAI-compatible self-hosted, Piper, dev-only mock), tenant routing, failover, circuit breaker, encrypted customer keys, admin catalog console. Managed vendor accounts and price lists are awaiting configuration |
| M04 | Telephony carriers, trunks, numbers | 6 | planned | Carrier onboarding to start early (X-4) |
| M05 | Agent builder and versioning | 4 | planned | |
| M06 | Inbound routing and queues | 6 | planned | |
| M07 | Outbound campaigns | 6 | planned | After M22-core (X-2, CR-023) |
| M08 | Call sessions and lifecycle | 3 | planned | |
| M09 | Conversation engine (STT → LLM → TTS) | 3 | planned | |
| M10 | Voice workers and real-time media | 3 | planned | |
| M11 | Workflows and follow-ups | 5 | planned | |
| M12 | Knowledge base and retrieval | 5 | planned | |
| M13 | Integrations | 5 | planned | |
| M14 | Support tickets and notifications | 5 | planned | |
| M15 | Usage metering, billing, plans | 2, 7 | partial | `modules/m15_usage`: append-only usage events in provider units, provider cost ledger, usage summary. Plans, invoices and charging in Phase 7 |
| M16 | Analytics and reporting | 7 | planned | |
| M17 | Platform administration and audit | 1, 7 | partial | Hash-chained audit log, tenant suspend/reactivate (`modules/m17_admin`) |
| M18 | Observability and operations | 1 | partial | Health, readiness, Prometheus metrics, OpenTelemetry hooks (`modules/m18_ops`) |
| M19–M25 | Healthcare modules (LLD v1.3) | 8 | planned | Healthcare mode stays disabled until the activation gate evidence exists |

## Requirement traceability (Phase 1)

| Requirement source | Requirement | Implementation | Test |
|---|---|---|---|
| LLD v1.3 §4 | Tenant isolation by PostgreSQL RLS, ENABLE + FORCE | `migrations/versions/0001_foundation.py` | `test_isolation.py::test_every_tenant_table_has_forced_rls` |
| LLD v1.3 §4 | Runtime role cannot bypass RLS | `infra/compose/postgres-init.sql` | `test_runtime_role_cannot_bypass_rls` |
| LLD v1.3 §4 | Composite tenant-aware foreign keys | `0001_foundation.py` | `test_sql_level_isolation` |
| HLD v1.3 security | MFA (TOTP) with encrypted secret | `m01_identity/service.py` | `test_mfa_enroll_and_login`, `test_mfa_secret_encrypted_at_rest` |
| HLD v1.3 security | Short-lived access tokens, refresh rotation, reuse detection | `m01_identity/service.py` | `test_refresh_rotation_and_reuse_detection` |
| HLD v1.3 security | Lockout and rate limiting | `core/ratelimit.py`, `m01_identity/service.py` | `test_lockout_after_repeated_failures` |
| HLD v1.0 §3 | Roles: owner, admin, agent designer, operator, viewer | `core/permissions.py` | `test_viewer_cannot_manage_and_denial_is_audited`, `test_role_rank_and_last_owner_guards` |
| HLD v1.0 §2 | India and US regional defaults (currency, time zone, language, date format) | `m02_tenant/regional.py` | `test_register_creates_owner_with_country_defaults`, `test_regional_settings_validation` |
| LLD v1.3 audit | Append-only, tamper-evident audit log with no secrets | `core/audit.py` | `test_audit_log_is_append_only_for_runtime_role`, `test_audit_hash_chain_links`, `test_audit_never_contains_secrets` |
| HLD v1.3 Super Admin | Separate admin surface, platform flag + MFA, audited with reason | `m17_admin/router.py` | `test_platform_admin_requires_flag_and_mfa` |
| Master prompt §IDOR | Cross-tenant identifiers return 404; tenant id in body ignored | `m02_tenant/router.py` | `test_api_cannot_reach_other_tenant_resources`, `test_tenant_id_in_body_is_ignored` |

## Requirement traceability (Phase 2)

| Requirement source | Requirement | Implementation | Test |
|---|---|---|---|
| HLD v1.0 §AI / master prompt Phase 2 | Provider abstraction for LLM, STT and TTS | `m03_ai/adapters/` | `test_ai_adapters.py` (12 contract tests) |
| HLD v1.3 / CR-012 | Ordered fallback and circuit breaker per provider | `m03_ai/gateway.py`, `m03_ai/breaker.py` | `test_failover_to_next_provider_and_breaker_opens` |
| HLD v1.0 §2 / CR-016 | Language-aware routing (en-IN, hi-IN, Hinglish, en-US) | `m03_ai/routing.py` | `test_language_and_capability_filters_explain_skips` |
| CR-018 | Customer-owned provider keys, encrypted, never returned | `m03_ai/router.py`, `core/security.py` | `test_customer_key_is_encrypted_never_returned_and_cost_borne_by_customer` |
| LLD v1.3 §4 | Tenant isolation for keys, routes and usage | `0002_ai_providers.py` (FORCE RLS) | `test_other_tenants_keys_and_usage_are_invisible` |
| Master prompt metering | Usage in provider units, idempotent, append-only | `m15_usage/metering.py` | `test_chat_tts_stt_metered_in_provider_units_with_cost`, `test_usage_is_idempotent_per_key`, `test_runtime_role_cannot_write_catalog_or_rewrite_usage` |
| Addendum (no invented vendors or prices) | Unconfigured vendors shown as awaiting configuration; no seeded commercial prices | `0002_ai_providers.py` | `test_catalog_marks_unconfigured_providers_awaiting_configuration` |
| HLD v1.3 healthcare | PHI routing only to providers with a signed BAA | `0002_ai_providers.py` check, `m03_ai/admin.py` | `test_admin_catalog_management_requires_mfa_admin_and_baa_for_phi` |
| Master prompt environments | Mock provider refused outside development and test | `m03_ai/routing.py` | `test_mock_provider_is_refused_in_production_like_environments` |
