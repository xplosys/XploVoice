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
| M04 | Telephony carriers, trunks, numbers | 6 | done (Phase 6 scope) | `modules/m04_telephony`: adapter contract, customer SIP trunks through LiveKit SIP, development-only simulated carrier, encrypted trunk secrets, numbers unique across tenants, destination policy and kill switch, verified and deduplicated carrier webhooks, usage in billing pulses (ADR-0009). Numbers from XploVoice await a carrier contract |
| M05 | Agent builder and versioning | 3, 4 | done (Phase 4 scope) | `modules/m05_agents`: all MP §9 fields, ten templates, immutable versions with content hashes and notes, readiness checks, lifecycle draft/testing/published/paused/archived, publish with a test-call gate, rollback, append-only publication history (ADR-0007). Knowledge base and tool grants are stored and run from Phase 5; transfer and recording run with telephony in Phase 6 |
| M06 | Inbound routing and queues | 6 | done (Phase 6 scope) | `modules/m06_inbound`: number-to-tenant routing, routes with queue and fallback, queue tick; hold audio not played |
| M07 | Outbound campaigns | 6 | done (Phase 6 scope) | `modules/m07_campaigns`: campaigns with four-eyes approval, contact import, policy engine with stored decisions, calling windows in local time, dialer, retries |
| M08 | Call sessions and lifecycle | 3 | done (Phase 3 scope) | `modules/m08_calls`: calls, order-tolerant lifecycle, append-only events and transcripts; 15-state lifecycle with transitions and carrier events from Phase 6 |
| M09 | Conversation engine (STT → LLM → TTS) | 3, 5 | done (Phase 5 scope) | `xplovoice_engine`: turn-taking, barge-in, clause-streamed TTS, guards, per-stage timing; `modules/m09_tools`: tool gateway, approvals, server-side tool loop with retrieval |
| M10 | Voice workers and real-time media | 3 | done (Phase 3 scope) | `xplovoice_worker`: LiveKit channel, Redis-stream dispatch with lease takeover; LiveKit hosting choice open (ADR-0006) |
| M11 | Workflows and follow-ups | 5 | done (Phase 5 scope) | `modules/m11_workflows`: booking calendars, holidays, appointments, leads with scoring, follow-ups |
| M12 | Knowledge base and retrieval | 5 | done (Phase 5 scope) | `modules/m12_knowledge`: scanned uploads, text extraction, chunking, full-text retrieval; embeddings awaiting configuration |
| M13 | Integrations | 5 | partial | `modules/m13_integrations`: event outbox, signed webhooks with retries; CRM and calendar connectors awaiting configuration |
| M14 | Support tickets and notifications | 5 | partial | `modules/m14_support`: tickets, comments, escalation tickets, approved templates; SMS and email delivery awaiting configuration |
| M15 | Usage metering, billing, plans | 2, 7 | partial | `modules/m15_usage`: append-only usage events in provider units, provider cost ledger, usage summary. Plans, invoices and charging in Phase 7 |
| M16 | Analytics and reporting | 7 | planned | |
| M17 | Platform administration and audit | 1, 7 | partial | Hash-chained audit log, tenant suspend/reactivate (`modules/m17_admin`) |
| M18 | Observability and operations | 1 | partial | Health, readiness, Prometheus metrics, OpenTelemetry hooks (`modules/m18_ops`) |
| M22-core | Consent and do-not-call (CR-023) | 6 | done | `modules/m22_consent`: consent records, do-not-call list, opt-out on calls; recording storage awaiting configuration |
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

## Requirement traceability (Phase 3)

| Requirement source | Requirement | Implementation | Test |
|---|---|---|---|
| MP §6, Phase 0 §E | One engine for every channel; channel adapter is the only channel-aware part | `xplovoice_engine/channel.py`, `xplovoice_worker/livekit_channel.py` | `test_browser_call_end_to_end_through_api_and_gateway` |
| MP §7, Phase 0 §G | Barge-in cuts speech; only heard words enter history | `xplovoice_engine/session.py` | `test_barge_in_cuts_reply_and_keeps_only_spoken_words`, `test_short_backchannel_does_not_interrupt` |
| Phase 0 §G | TTS starts on the first clause | `xplovoice_engine/clauses.py` | `test_clause_splitter_starts_speech_on_first_clause` |
| Phase 3 gate | Worker kill-and-recover | `xplovoice_worker/queue.py`, `m08_calls/internal.py` | `test_worker_killed_mid_call_is_recovered_by_another_worker` (SIGKILL) |
| Phase 3 gate | First latency benchmark | `scripts/voice_benchmark.py` | [benchmark](benchmarks/phase-3-latency.md) |
| MP §9 | Calls pin an immutable agent version | `0003_voice_engine.py`, `m05_agents` | `test_agent_versions_are_immutable_and_calls_pin_them` |
| CR-003 | Order-tolerant, idempotent call events | `m08_calls/lifecycle.py` | `test_late_or_repeated_state_updates_never_move_a_call_backwards`, `test_recording_is_idempotent` |
| CR-012 | No provider: fixed message, clean end | `xplovoice_engine/session.py` | `test_no_provider_plays_fixed_message_and_ends`, `test_call_with_no_provider_ends_cleanly_as_failed` |
| Phase 0 §H voice sessions | Room-scoped, short-lived tokens; opaque rooms | `m08_calls/livekit.py` | `test_voice_session_token_is_scoped_short_lived_and_dispatched` |
| LLD v1.3 §5 | Workers use only /internal/v1 with a worker credential scoped to one call | `m08_calls/internal.py` | `test_internal_api_requires_worker_key_and_matching_call_token` |
| LLD v1.3 §4 | Calls, transcripts, agents isolated per tenant | `0003_voice_engine.py` (FORCE RLS) | `test_calls_are_isolated_between_tenants`, `test_every_tenant_table_has_forced_rls` |
| Phase 0 §E guards | Per-call duration and silence limits | `xplovoice_engine/session.py` | `test_max_duration_guard`, `test_silence_prompts_then_ends` |

## Requirement traceability (Phase 5)

| Requirement source | Requirement | Implementation | Test |
|---|---|---|---|
| Phase 0 O6, addendum G | Retrieval reads only the tenant's granted, active knowledge | `m12_knowledge/service.py`, `0005_knowledge_tools.py` (FORCE RLS) | `test_retrieval_reads_only_the_agents_own_tenant_and_granted_active_knowledge` |
| Addendum G | Retrieved text is data, not instructions | `m12_knowledge/service.py::reference_block` | `test_retrieved_text_is_marked_as_data_not_instructions` |
| CR-020 | Uploads scanned before storage; typed by content | `m12_knowledge/ingest.py` | `test_documents_are_scanned_typed_by_content_chunked_and_searchable`, `test_scanner_is_required_outside_development` |
| Phase 0 O7, addendum G | Tools run only when granted, enabled, valid and once | `m09_tools/gateway.py` | `test_tools_run_only_when_granted_enabled_valid_and_never_twice` |
| Addendum G | Sensitive actions need a person's approval | `m09_tools/gateway.py::decide` | `test_sensitive_actions_wait_for_a_person` |
| Addendum G | Tool failures are contained and timed out | `m09_tools/gateway.py` | `test_tool_failures_are_contained` |
| Addendum H | Native booking, leads, follow-ups, tickets | `m11_workflows`, `m14_support` | `test_booking_by_chat_runs_tools_server_side_and_records_everything`, `test_availability_respects_hours_notice_holidays_and_bookings`, `test_leads_and_follow_ups_from_a_chat`, `test_tickets_from_tools_and_from_escalation` |
| Addendum (no invented vendors) | Messages never reported as sent without a provider | `m14_support/service.py` | `test_only_approved_messages_are_sent_and_never_claimed_delivered` |
| CR-021 | Signed, retried, isolated webhooks; SSRF guard | `m13_integrations/dispatch.py` | `test_webhook_urls_must_be_public_https`, `test_events_are_signed_delivered_retried_and_isolated`, `test_dead_after_max_attempts` |
| MP §6 | Same tools in voice calls through the worker API | `m08_calls/internal.py`, `xplovoice_engine/backend.py` | `test_tools_during_a_voice_call_go_through_the_worker_api` |


## Requirement traceability (Phase 6)

| Requirement source | Requirement | Implementation | Test |
|---|---|---|---|
| Addendum D | Carrier abstraction; LiveKit SIP trunks, calls and transfer | `m04_telephony/adapters/` | `test_livekit_sip_adapter_requests` |
| Addendum E, CR-003 | 15 states; idempotent, order-tolerant, verified events | `m08_calls/lifecycle.py`, `m04_telephony/service.py::ingest`, `m04_telephony/webhooks.py` | `test_carrier_webhooks_are_verified_deduplicated_and_order_tolerant`, `test_livekit_webhook_routes_sip_callers_and_ends_calls` |
| Addendum I inbound, CR-009 | Number-to-tenant routing, queue, fallback, kill switch | `m06_inbound/service.py` | `test_inbound_routes_queues_and_falls_back`, `test_queue_times_out_to_fallback_and_hangup`, `test_inbound_unknown_unpublished_and_paused`, `test_inbound_calls_stay_in_their_organisation` |
| Addendum I outbound, CR-009 | Approval, consent, do-not-call, window, caps, retries | `m07_campaigns/` | `test_campaigns_need_approval_by_another_person`, `test_consent_and_do_not_call_block_before_any_carrier_request`, `test_toll_fraud_caps`, `test_calling_window_in_the_persons_local_time`, `test_window_defers_and_no_window_blocks`, `test_retry_then_exhausted_and_carrier_outcomes` |
| Addendum I, CR-011 | Opt-out on a call; consent records; recording consent | `m22_consent/service.py`, `m08_calls/internal.py` | `test_opt_out_on_a_call_stops_every_campaign`, `test_recording_consent_on_the_call`, `test_engine_phone.py` |
| Addendum D | Transfer with destination checks | `m08_calls/internal.py::transfer` | `test_transfer_success_failure_and_destination_rules`, `test_transfer_success_ends_the_agent_leg`, `test_failed_transfer_comes_back_and_takes_a_message` |
| Addendum D | Billing pulses | `m04_telephony/service.py::finalize` | `test_usage_is_billed_in_carrier_pulses` |
| Addendum D | Keypad tones (DTMF) | `xplovoice_engine/session.py`, `xplovoice_worker/livekit_channel.py` | `test_keypad_digits_become_a_typed_reply_and_zero_asks_for_a_person` |
