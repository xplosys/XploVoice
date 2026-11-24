# Architecture Change Request Register: AI Voice Addendum

| Field | Value |
|---|---|
| Procedure | Xplosys Client SaaS Development Governance Handbook v1.0, §13.1 and SOP-020 |
| Raised against | XploVoice HLD v1.3 / LLD v1.3 |
| Raised from | [Traceability matrix](addendum-traceability-matrix.md) |
| Date | 24 November 2026 |
| Approval | **All CRs Pending.** Per §13.1 step 6, nothing that changes the baseline gets implemented until approval is recorded below. |

Effort estimates are rough design-and-build sizes for a small team, to be refined during planning:
**S** ≤ 1 week, **M** 1–3 weeks, **L** 3–6 weeks, **XL** > 6 weeks. The proposed tables and APIs
are suggestions to start from for the LLD update, not approved design.

## Summary

| CR | Title | Requirements | Modules | Priority | Effort | Status |
|---|---|---|---|---|---|---|
| CR-001 | Core LLD baseline for M01–M18 | ADD-R-01, R-05, all | M01–M18 | **Blocker** | L | Pending |
| CR-002 | Common voice engine and channel adapter contract (incl. browser/WebRTC) | A, B | M09, M10 | High | L | Pending |
| CR-003 | Call lifecycle state machine and idempotent event processing | E, D-10, F-07 | M04, M06, M07, M08 | High | M | Pending |
| CR-004 | Latency instrumentation and benchmark harness | C | M18, M10 | High | M | Pending |
| CR-005 | Telephony/SIP provider adapters and capability registry | D, A-04/05, R-03, R-13 | M04, M03 | High | L | Pending |
| CR-006 | Agent orchestration configuration and versioned agent schema | F, B-10, H-07 | M05, M09 | High | M | Pending |
| CR-007 | Tool gateway and tenant-scoped RAG authorization | G, L-04 | M09, M12 | High | M | Pending |
| CR-008 | Native business workflows (follow-up, holidays, support tickets) | H, G-07 | M11, M13, M14, M02 | Medium | L | Pending |
| CR-009 | Inbound routing policy and outbound campaign policy engine | I, A-06, H-04 | M06, M07 | High | L | Pending |
| CR-010 | Worker and queue architecture | J, B-13 | M10, M18 | High | M | Pending |
| CR-011 | Recording/consent/retention for standard (non-healthcare) tenants | K | M22, M24, M23, M08 | Medium | M | Pending |
| CR-012 | Platform-wide failover and reliability policy | L, B-12, D-11 | M03, M04, M09 | High | M | Pending |
| CR-013 | Concurrency, capacity and admission control | M | M15, M10, M02 | High | M | Pending |
| CR-014 | Per-call tracing span model and monitoring catalogue | N, M-06 | M18, M16 | Medium | S | Pending |
| CR-015 | Core-platform acceptance test catalogue (O1–O16) | O, R-14 | All | High | M | Pending |
| CR-016 | Hinglish and country/language configuration registry | Q, B-11 | M02, M03, M09 | Medium | M | Pending |
| CR-017 | Vertical-slice definition of done, dependency graph and status register | P | All (process) | High | S | Pending |

---

## CR-001: Core LLD baseline for M01–M18

- **Requested outcome:** publish or recover the official LLD module catalogue, tables, APIs and tests for M01–M18.
- **Business reason:** the addendum requires mapping to "existing official LLD module IDs". LLD v1.3 refers to M01–M18 but doesn't define them, and no earlier LLD is in the document set.
- **Interim action taken:** provisional IDs are assigned in [module-catalogue.md](module-catalogue.md), chosen to fit every LLD v1.3 dependency. The traceability matrix uses those IDs.
- **Impact:** *Requirements:* every row in the matrix. *Design:* core tables for tenants, users, agents, agent_versions, calls, call_events, campaigns, contacts, appointments, kb_documents/chunks, usage_ledger and so on, and the core `/v1/*` APIs. *Security:* RLS rules (LLD §4) need tables to apply to. *Testing:* core isolation tests.
- **Acceptance impact:** gate O16 can't be fully specified without it.
- **Recommendation:** if LLD v1.0–v1.2 exists, add it to the document set and re-key the matrix. If not, approve the provisional catalogue as LLD v1.4 §2 and write the core LLD sections module by module as part of each vertical slice (CR-017).
- **Approval:** ☐ Pending.

## CR-002: Common voice engine and channel adapter contract

- **Requested outcome:** one conversation engine (M09) behind a `ChannelAdapter` contract, with adapters for WebRTC/browser, PSTN-via-SIP and SIP-direct. Every channel reaches the engine through a LiveKit room, so the engine never branches on channel type.
- **Reason:** addendum A and R-02. The HLD pipeline covers PSTN/SIP only, and browser voice isn't in the HLD.
- **Proposed design:**
  - Adapter interface: `open_session`, `audio_in`, `audio_out`, `dtmf`, `transfer`, `hangup`, `capabilities`.
  - Browser channel: the dashboard and an embeddable widget get a short-lived, scoped LiveKit participant token from `POST /v1/voice/sessions`. The same worker job type serves both browser and phone.
  - Pipeline stages are explicit and individually timed: ingest, VAD, endpointing, STT (partial/final), language ID, context, LLM, RAG, tools, TTS, egress.
  - Turn-taking config per agent: silence timeout, max silence count, end-of-turn sensitivity, barge-in on/off, minimum interruption duration.
  - Interruption cancels in-flight TTS and the LLM stream, and only committed text goes into conversation history.
- **Data:** `voice_sessions` (id, tenant_id, call_id, channel, livekit_room, worker_id, region, started_at, ended_at).
- **Security:** browser tokens scoped to one room with a short TTL. Public widget sessions are rate-limited and bot-protected.
- **Testing:** O1, O4, O5.
- **Effort:** L. **Approval:** ☐ Pending.

## CR-003: Call lifecycle state machine and idempotent event processing

- **Requested outcome:** a formal call state machine with the 15 addendum states, allowed transitions, terminal reasons and idempotent, order-tolerant event application.
- **Reason:** addendum E. The LLD only has a consent state machine.
- **Proposed design:**
  - States: INITIATED → QUEUED → ROUTING → RINGING → ANSWERED → CONNECTED → IN_PROGRESS ⇄ ON_HOLD → TRANSFERRING → terminal {COMPLETED, FAILED, BUSY, NO_ANSWER, CANCELLED, DISCONNECTED}.
  - Terminal states are absorbing. A late event for a terminal call is recorded but doesn't change the state.
  - Events are persisted first (`call_events`, unique on `(tenant_id, provider, provider_event_id)`) and then applied by a reducer that uses provider timestamps and a per-call sequence. Out-of-order events can't move a call backwards.
  - Each call stores direction, channel, agent_version_id, stt/llm/tts provider and model versions, provider call IDs, timestamps per state and terminal_reason.
- **Data:** `calls`, `call_events`, `call_state_transitions`, `call_provider_refs`.
- **Testing:** O9, O10 (duplicate webhook replay creates one action and one billing entry).
- **Effort:** M. **Approval:** ☐ Pending.

## CR-004: Latency instrumentation and benchmark harness

- **Requested outcome:** per-stage latency metrics, a *defined test workload*, a repeatable benchmark harness and dashboards. The 1.5 s p95 stays a target until benchmark evidence exists.
- **Reason:** addendum C. The HLD names four of the eight stages and doesn't define a workload.
- **Proposed design:**
  - Spans and histograms: `ingest`, `vad_endpoint`, `stt_partial_first`, `stt_final`, `llm_first_token`, `tool_exec`, `tts_first_audio`, `first_audible_response`, `response_complete`.
  - Labels: provider, model, language, region, call_type, channel. There's never a tenant-identifying or PHI label.
  - Workload v0: synthetic consented audio sets for Hindi, Hinglish, Indian English and US English; a "common turn" defined as no tool call, at most 2 RAG chunks and replies of at most 40 tokens; N concurrent calls per worker; browser and SIP paths.
  - The harness runs in staging, and results are stored as `compliance_evidence` (M25) with the commit SHA.
- **Testing:** O15.
- **Effort:** M. **Approval:** ☐ Pending.

## CR-005: Telephony/SIP provider adapters and capability registry

- **Requested outcome:** an adapter per carrier, plus a data-driven capability registry so routing never assumes features match across providers.
- **Reason:** addendum D, R-03, R-13. The LLD has no telephony schema.
- **Proposed design:**
  - `telephony_providers`, `provider_capabilities` (country, number types, inbound/outbound, SIP REFER/transfer modes, DTMF modes, recording, SIP/TLS + SRTP, registration vs IP auth, billing pulse e.g. 60/60 or 1/1, rate card ref, verified_at, evidence_ref).
  - `sip_trunks` (tenant-owned or managed, auth mode, credential secret ref), `phone_numbers` (E.164, DID, provider, tenant, agent mapping, status), `destination_policies` (allow/deny prefixes, premium-rate block).
  - Routing policy evaluates tenant config, country, capability match, provider health, cost and reliability score.
  - Health checks for each provider (`provider_health`), and webhook signature verification for each adapter.
  - A capability is only marked available with written provider confirmation or a passing sandbox test. That enforces "no fabricated capabilities".
- **Testing:** O2, O3, O8, O12.
- **Effort:** L. **Approval:** ☐ Pending.

## CR-006: Agent orchestration configuration and versioned agent schema

- **Requested outcome:** an immutable `agent_versions` schema holding everything the orchestrator needs, and every call pinned to it.
- **Reason:** addendum F, B-10, H-07. The HLD describes the lifecycle but the LLD has no schema.
- **Proposed design:** `agents`, plus `agent_versions` (immutable after publish, content hash). The version holds:
  - instructions, language set, STT/LLM/TTS selection with fallback order, voice ID, speed and other voice settings
  - KB bindings, tool allowlist, call limits (max duration, tokens, spend), timeout/retry policy
  - escalation rules (keywords, sentiment, repeated failure, explicit request), handoff target, termination rules

  Calls reference `agent_version_id` and also record the resolved provider and model versions actually used.
- **Effort:** M. **Approval:** ☐ Pending.

## CR-007: Tool gateway and tenant-scoped RAG authorization

- **Requested outcome:** a tool gateway in which each tool has a registered JSON schema, required permission, timeout, idempotency mode, sensitivity class and approval requirement. RAG is filtered by tenant and agent before ranking.
- **Reason:** addendum G and L-04.
- **Proposed design:**
  - `tool_definitions`, `agent_tool_grants` and `tool_invocations` (idempotency_key unique, status PENDING/EXECUTING/SUCCEEDED/FAILED/UNKNOWN, input hash, result ref, audit). Before a retry, the gateway checks the invocation status first.
  - Sensitive actions such as cancelling an appointment need caller confirmation in the conversation, or human approval in the queue.
  - RAG queries run under tenant RLS with an `agent_id` / KB binding filter. Retrieved text is treated as untrusted and can't trigger tools by itself.
  - There are no generic SQL, shell or HTTP tools.
- **Testing:** O6, O7, O10.
- **Effort:** M. **Approval:** ☐ Pending.

## CR-008: Native business workflows

- **Requested outcome:** native workflow modules for follow-ups, business-hours and holiday calendars, and support tickets, alongside the appointments, leads and notifications already in the HLD.
- **Reason:** addendum H and G-07. The HLD doesn't cover ticketing, holiday calendars or follow-up sequences.
- **Proposed design:**
  - `business_calendars` / `holiday_calendars` (tenant, IANA tz, country holiday packs plus custom dates)
  - `follow_up_tasks`
  - `support_tickets` (minimal, inside M13 CRM)
  - External CRM/calendar integrations sync to these records and don't replace them.
- **Effort:** L. **Approval:** ☐ Pending.

## CR-009: Inbound routing policy and outbound campaign policy engine

- **Requested outcome:** separate inbound and outbound policy models.
  - **Inbound:** number → tenant → routing rule (hours, holiday, caller attributes) → agent, plus welcome message, queue/overflow and fallback.
  - **Outbound:** a policy engine evaluated per dial attempt.
- **Reason:** addendum I. The HLD §7 describes the outbound gate, but the LLD has no tables, and there's no inbound queue design.
- **Proposed design:**
  - `inbound_routes`, `campaigns`, `campaign_contacts`, `suppression_list` (DNC, opt-out, tenant and platform scope), `dial_attempts` and `policy_decisions` (inputs, result and policy version for each attempt).
  - Country packs carry calling windows and rules for India (TRAI/TCCCPR) and the US (TCPA/DNC/state rules). These are configurable, need legal review, and fail closed.
  - Campaigns need an approval step and have rate and concurrency caps. There's no API for an unrestricted bulk dial.
- **Testing:** O2, O3, O8.
- **Effort:** L. **Approval:** ☐ Pending.

## CR-010: Worker and queue architecture

- **Requested outcome:** a specification for voice workers and background workers.
- **Reason:** addendum J and B-13. The HLD names the components, but there's no LLD.
- **Proposed design:**
  - Voice workers run as separate Docker services and register with LiveKit agent dispatch.
  - `worker_heartbeats` in Redis with a TTL, plus a durable registry in PostgreSQL. Workers drain on SIGTERM and refuse new jobs while finishing active calls.
  - Background jobs run on Redis-backed queues (e.g. arq/RQ/Celery, to be decided by ADR) with retry, backoff, a dead-letter queue and per-queue concurrency.
  - Backpressure: admission is refused when worker capacity is exhausted (CR-013).
  - Region is a worker label (`in`, `us`). Dispatch picks a worker region from the tenant's region and the carrier's media region.
  - No Kubernetes. Docker Compose with resource limits.
- **Testing:** O14.
- **Effort:** M. **Approval:** ☐ Pending.

## CR-011: Recording, consent and retention for standard tenants

- **Requested outcome:** apply the M22/M24/M23 mechanisms to *all* tenants, not only healthcare tenants, and add a per-agent recording setting.
- **Reason:** addendum K. LLD v1.3 frames consent, retention and access audit around healthcare and PHI.
- **Proposed design:**
  - Make `consent_records`, retention policies and recording access audit general platform tables. Healthcare tenants add stricter policy on top.
  - Add `recording_mode` and `transcription_mode` to `agent_versions`.
  - Add a general `recording_access_audit` (or broaden `phi_access_audit_logs`, to be decided by ADR).
  - Transcript redaction (PII patterns) for standard tenants.
- **Testing:** O13.
- **Effort:** M. **Approval:** ☐ Pending.

## CR-012: Platform-wide failover and reliability policy

- **Requested outcome:**
  - Fallback chains for STT, LLM, TTS and telephony, with circuit breakers (closed/open/half-open per provider and region) and exponential backoff with full jitter.
  - Bounded retries, and degradation steps from cached prompt, to apology and handoff, to graceful end.
- **Reason:** addendum L, B-12, D-11. LLD §7 defines the fallback rule only for healthcare.
- **Proposed design:** a per-capability `fallback_policy` in agent versions. Breaker state lives in Redis. Mid-call provider swaps are allowed for STT and TTS where the stream can be re-established. A swap is logged in call events, and the fallback must pass the same eligibility checks (keeping LLD §7 for healthcare).
- **Testing:** O9.
- **Effort:** M. **Approval:** ☐ Pending.

## CR-013: Concurrency, capacity and admission control

- **Requested outcome:** layered limits (platform → plan → tenant → campaign → provider), checked atomically at admission, with overload protection.
- **Reason:** addendum M. Neither document covers it.
- **Proposed design:**
  - Redis atomic counters or semaphores (Lua) for active calls per tenant, plan, platform and provider, with leases that expire if a worker dies.
  - `plan_limits` and `tenant_limits` tables. Spend limits come from the usage ledger (M15).
  - When a limit is exceeded: inbound calls go to the queue or overflow message, and outbound attempts are deferred.
- **Testing:** O11.
- **Effort:** M. **Approval:** ☐ Pending.

## CR-014: Per-call tracing span model and monitoring catalogue

- **Requested outcome:**
  - A defined trace hierarchy: call → telephony leg → SIP session → LiveKit room → worker job → turn → STT/LLM/tool/TTS spans → billing event.
  - A catalogue of metrics and alerts for the 14 signals in addendum N.
- **Reason:** addendum N and M-06. LLD §14 picks the tools but doesn't define the span model, and doesn't cover transfer success, call quality (MOS/jitter/packet loss from LiveKit stats) or cost per minute.
- **Effort:** S. **Approval:** ☐ Pending.

## CR-015: Core-platform acceptance test catalogue

- **Requested outcome:** test IDs (for example VX-001…) for gates O1–O16, in the same style as LLD §12 HC-001…HC-012, each with setup, steps, expected result and the evidence to capture.
- **Reason:** addendum O and R-14. The LLD tests cover healthcare only.
- **Effort:** M. **Approval:** ☐ Pending.

## CR-016: Hinglish and country/language configuration registry

- **Requested outcome:**
  - Add Hinglish (Hindi–English code-switching) as a first-class language profile.
  - Add a `languages` and `country_profiles` registry (currency, timezone, number format, carriers, consent and regulatory pack), plus language identification and mid-call switching.
- **Reason:** addendum Q and B-11. HLD §2 lists Hindi and Indian English separately, and doesn't mention code-switching or switching language mid-call.
- **Proposed design:** language profiles map to an STT model, TTS voice and LLM prompt locale. Hinglish needs an STT provider benchmarked on code-switched audio (CR-004 workload).
- **Effort:** M. **Approval:** ☐ Pending.

## CR-017: Vertical-slice definition of done, dependency graph and status register

- **Requested outcome:**
  - Adopt the 14-element vertical-slice definition of done from addendum P.
  - Keep a module dependency graph and an implementation status register in the repo.
  - Gate dependent modules on acceptance.
- **Reason:** addendum P. This is a delivery-process change, related to Governance Handbook SOP-007, SOP-008 and SOP-009.
- **Effort:** S. This is plan step 2. **Approval:** ☐ Pending.

---

## Approval record

| CR | Decision | Approver | Date | Notes |
|---|---|---|---|---|
| CR-001 … CR-017 | | | | |
