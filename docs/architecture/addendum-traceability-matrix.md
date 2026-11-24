# Traceability Matrix: AI Voice Architecture Addendum → LLD

| Field | Value |
|---|---|
| Source requirement | [Mandatory Addendum: Detailed AI Voice Architecture](../requirements/addendum-ai-voice-architecture.md), sections A–R |
| Design baseline | HLD v1.0, HLD v1.3, LLD v1.3 |
| Module IDs | [Module catalogue](module-catalogue.md). M01–M18 are **provisional** (CR-001) |
| Change requests | [Change request register](change-requests.md) |
| Status | Draft for review, 24 November 2026 |

## How to read this

- **Req ID** is `ADD-<section>-<nn>` and is stable, so tasks, tests and PRs can cite it.
- **Modules** gives the owning module first, then the contributing modules.
- **LLD tables / APIs / controls** cite what LLD v1.3 actually defines. "—" means the LLD defines nothing for this yet.
- **Gate** refers to the acceptance gate numbers in addendum section O (O1–O16) and to LLD test IDs (HC-xxx).
- **Coverage** is one of:
  - **Covered:** LLD v1.3 specifies it.
  - **HLD only:** the HLD describes it, but there's no LLD detail (no tables or APIs).
  - **Gap:** neither the HLD nor the LLD covers it.
- Any requirement that isn't **Covered** links to a change request. Nothing has been dropped silently.

> **Headline finding:** LLD v1.3 specifies only the Healthcare overlay (M19–M25). For the core platform
> (M01–M18) the LLD has no tables, APIs or tests, so most voice requirements show as **HLD only** at best.
> CR-001 asks for the core LLD baseline. CR-002 to CR-016 cover the specific gaps.

---

## A. Common AI Voice Engine

| Req ID | Requirement | Modules | LLD tables | LLD APIs | Controls | Gate | Coverage | CR |
|---|---|---|---|---|---|---|---|---|
| ADD-A-01 | One reusable conversation engine for all channels, not duplicated per channel | M09, M10 | — | — | HLD §3 boundaries | O1, O2, O3 | HLD only | CR-002 |
| ADD-A-02 | All channels share orchestration, context, tools, KB, security, billing | M09, M05, M12, M15 | — | — | HLD §3 | O1–O3 | HLD only | CR-002 |
| ADD-A-03 | Browser/WebRTC voice channel | M10, M09 | — | — | — | O1 | **Gap**: HLD covers PSTN/SIP only | CR-002 |
| ADD-A-04 | PSTN calls | M04, M06, M10 | — | — | HLD §7 | O2 | HLD only | CR-005 |
| ADD-A-05 | SIP-based calls | M04, M10 | — | — | HLD v1.3 §4 (carrier allowlist, SIP/TLS, SRTP) | O2 | HLD only | CR-005 |
| ADD-A-06 | Inbound and outbound calls | M06, M07 | — | — | HLD §7 outbound gate | O2, O3 | HLD only | CR-009 |
| ADD-A-07 | Future channels through adapters | M10, M03 | — | — | — | — | **Gap**: no channel adapter contract | CR-002 |

## B. Real-Time Voice Processing Pipeline

| Req ID | Requirement | Modules | LLD tables | LLD APIs | Controls | Gate | Coverage | CR |
|---|---|---|---|---|---|---|---|---|
| ADD-B-01 | Streaming pipeline: ingest → VAD → STT → transcript → lang ID → context → LLM → RAG → tools → TTS → egress | M10, M09 | — | — | HLD §5 pipeline | O1, O4 | HLD only (lang ID step missing) | CR-002 |
| ADD-B-02 | Stream instead of waiting for complete responses | M09, M03 | — | — | — | O4 | HLD only | CR-002 |
| ADD-B-03 | Partial transcript support | M09, M03 | — | — | — | O4 | HLD only (`receive_partial` adapter) | CR-002 |
| ADD-B-04 | Voice activity detection | M10 | — | — | — | O4 | HLD only | CR-002 |
| ADD-B-05 | Silence detection, configurable timeouts | M10, M05 | — | — | — | — | **Gap** | CR-002 |
| ADD-B-06 | End-of-turn detection | M10 | — | — | — | O15 | HLD only | CR-002 |
| ADD-B-07 | Barge-in / interruption | M10, M09 | — | — | — | O5 | HLD only | CR-002 |
| ADD-B-08 | Cancel obsolete TTS/LLM after interruption | M09, M03 | — | — | — | O5 | HLD only (`cancel` on LLM adapter) | CR-002 |
| ADD-B-09 | Conversation state management | M09, M08 | — | — | Redis never sole source of truth (HLD §6) | — | HLD only | CR-002 |
| ADD-B-10 | Configurable speaking speed / voice settings | M05, M03 | — | — | — | — | **Gap** | CR-006 |
| ADD-B-11 | Language identification and mid-call switching | M09, M03 | — | — | — | — | **Gap** | CR-016 |
| ADD-B-12 | Provider timeout and fallback | M09, M03 | — | — | LLD §7 (healthcare fallback rule) | O9 | Partial (healthcare only) | CR-012 |
| ADD-B-13 | Disconnect and recovery handling | M10, M06 | — | — | — | O9, O14 | **Gap** | CR-003, CR-010 |

## C. Voice Latency and Quality

| Req ID | Requirement | Modules | LLD tables | LLD APIs | Controls | Gate | Coverage | CR |
|---|---|---|---|---|---|---|---|---|
| ADD-C-01 | p95 common-turn latency target < 1.5 s under a defined workload | M18, M10 | — | — | HLD §5 (target, not a guarantee) | O15 | HLD only (no workload defined) | CR-004 |
| ADD-C-02 | Per-stage timings: ingest, VAD/endpoint, STT partial/final, LLM first token, tool, TTS first audio, first audible, completion | M18, M10, M09 | — | — | LLD §14 (OTel) | O15 | Partial (4 of 8 stages in HLD) | CR-004 |
| ADD-C-03 | Make no claims without benchmark evidence | M25, M18 | `compliance_evidence` | `GET /v1/compliance/evidence` | — | O15 | Partial (evidence store exists) | CR-004 |
| ADD-C-04 | Dashboards and load tests by provider, model, language, region, call type | M18, M16 | — | — | LLD §14 label rules (no PHI) | O15 | **Gap** | CR-004 |

## D. Telephony and SIP Provider Abstraction

| Req ID | Requirement | Modules | LLD tables | LLD APIs | Controls | Gate | Coverage | CR |
|---|---|---|---|---|---|---|---|---|
| ADD-D-01 | Several telephony providers via independent adapters; no carrier logic in the business layer | M04, M03 | — | — | HLD §3 boundaries | — | HLD only | CR-005 |
| ADD-D-02 | Customer-owned SIP trunks | M04 | — | — | Secret refs only (HLD §7) | O2 | HLD only | CR-005 |
| ADD-D-03 | XploVoice-managed numbers where contractually available | M04, M17 | — | — | — | — | HLD only | CR-005 |
| ADD-D-04 | DID / number management | M04 | — | — | E.164 (HLD §6) | — | HLD only | CR-005 |
| ADD-D-05 | Inbound / outbound routing | M04, M06, M07 | — | — | — | O2, O3 | HLD only | CR-005 |
| ADD-D-06 | SIP registration, auth, trunk configuration | M04 | — | — | HLD v1.3 §4 SIP/TLS, toll-fraud controls | — | **Gap** (no trunk schema) | CR-005 |
| ADD-D-07 | LiveKit SIP integration | M10, M04 | — | — | Scoped participant tokens (HLD v1.3 §4) | O2 | HLD only | CR-005 |
| ADD-D-08 | Call transfer | M04, M10 | — | — | — | O8 | HLD only | CR-005 |
| ADD-D-09 | DTMF where required | M04, M10 | — | — | — | — | **Gap** | CR-005 |
| ADD-D-10 | Call status webhooks | M04 | — | — | Signature, timestamp, replay window, idempotent (HLD §7) | O10 | HLD only | CR-003 |
| ADD-D-11 | Provider error handling and health checks | M04, M18 | — | — | — | O9 | **Gap** | CR-005, CR-012 |
| ADD-D-12 | Number and destination restrictions | M04, M07 | — | — | Carrier allowlist, toll-fraud (HLD v1.3) | — | HLD only | CR-005 |
| ADD-D-13 | Carrier billing pulses and pricing units | M15, M04 | — | — | LLD §14 (pulses/seconds metered separately) | O12 | Partial | CR-005 |
| ADD-D-14 | Routing policy by tenant, country, availability, cost, reliability, capability | M04, M03 | `vendor_compliance_records` (healthcare) | `GET /v1/vendors/eligibility` | LLD §7 | — | Partial (healthcare only) | CR-005 |
| ADD-D-15 | Per-provider capability registry; don't assume feature parity | M04, M03 | — | — | — | — | **Gap** | CR-005 |

## E. Call Lifecycle Management

| Req ID | Requirement | Modules | LLD tables | LLD APIs | Controls | Gate | Coverage | CR |
|---|---|---|---|---|---|---|---|---|
| ADD-E-01 | Formal call state machine (15 states: Initiated … Disconnected) | M06, M07, M08 | — | — | — | O9 | **Gap** (only the consent state machine exists, LLD §8) | CR-003 |
| ADD-E-02 | Store timestamps, provider IDs, agent version, tenant, direction, channel, usage events, terminal reason | M08, M15 | — | — | UTC (LLD §4) | O12 | **Gap** | CR-003 |
| ADD-E-03 | Handle duplicate, delayed and out-of-order events safely; idempotent processing | M04, M08 | — | — | HLD §8 (persist then dedupe by provider event ID) | O9, O10 | HLD only | CR-003 |

## F. AI Agent Orchestration

| Req ID | Requirement | Modules | LLD tables | LLD APIs | Controls | Gate | Coverage | CR |
|---|---|---|---|---|---|---|---|---|
| ADD-F-01 | Agent identity, version, system instructions | M05 | — | — | — | — | HLD only | CR-006 |
| ADD-F-02 | Conversation state, language, model, STT/TTS selection | M09, M05, M03 | — | — | LLD §7 provider eligibility | — | HLD only | CR-006 |
| ADD-F-03 | KB access and tool permissions per agent | M05, M12, M09 | — | — | HLD §3 (only registered tools) | O6, O7 | HLD only | CR-007 |
| ADD-F-04 | Call-level limits, timeout/retry policies | M09, M15 | — | — | HLD §5 (token/duration/spend ceilings) | O11 | HLD only | CR-006 |
| ADD-F-05 | Escalation rules, human handoff, session termination | M09, M10, M04 | — | — | — | O8 | HLD only | CR-006 |
| ADD-F-06 | Immutable agent versions | M05 | — | — | HLD §4 agent lifecycle | — | HLD only | CR-006 |
| ADD-F-07 | Each call records exact agent version and provider/model versions | M08, M05 | — | — | — | — | Partial (HLD covers agent version only) | CR-003, CR-006 |

## G. RAG and Business Tool Execution

| Req ID | Requirement | Modules | LLD tables | LLD APIs | Controls | Gate | Coverage | CR |
|---|---|---|---|---|---|---|---|---|
| ADD-G-01 | Tenant-isolated RAG | M12 | — | — | RLS + composite FKs (LLD §4); vector isolation test (LLD §16) | O6, O16 | Partial (rules only, no KB schema) | CR-007 |
| ADD-G-02 | Controlled tool gateway with the 8 example tools | M09 + M11, M13, M14, M04 | — | — | HLD v1.3 §8 typed schemas | O7 | HLD only | CR-007 |
| ADD-G-03 | Authorize before retrieval and before every tool action | M09, M01 | — | — | LLD §5 deny by default | O6, O7 | Partial | CR-007 |
| ADD-G-04 | Schema-validated tool inputs | M09 | — | — | HLD v1.3 §8 | O7 | HLD only | CR-007 |
| ADD-G-05 | Timeouts, idempotency, audit, retry, human approval for sensitive actions | M09, M17 | `phi_access_audit_logs` (PHI only) | — | HLD v1.3 §8 (confirmation for consequential actions) | O7, O10 | Partial | CR-007 |
| ADD-G-06 | No model-generated SQL, shell, or arbitrary external requests | M09 | — | — | HLD §3 | O7, O16 | HLD only | CR-007 |
| ADD-G-07 | Support ticket creation | M13 | — | — | — | — | **Gap**: no ticketing in HLD | CR-008 |

## H. Native Business Workflows

| Req ID | Requirement | Modules | LLD tables | LLD APIs | Controls | Gate | Coverage | CR |
|---|---|---|---|---|---|---|---|---|
| ADD-H-01 | Appointment scheduling | M11 | — | — | HLD §10 race-safe booking | — | HLD only | CR-008 |
| ADD-H-02 | Lead capture and qualification, CRM activity | M13 | — | — | — | — | HLD only | CR-008 |
| ADD-H-03 | Customer follow-up | M13, M14 | — | — | — | — | **Gap** | CR-008 |
| ADD-H-04 | Campaign execution | M07 | — | — | HLD §7 | O3 | HLD only | CR-009 |
| ADD-H-05 | Notifications | M14 | — | — | Transactional outbox (HLD §8) | — | HLD only | CR-008 |
| ADD-H-06 | Business hours and holiday calendars | M02, M11, M06 | — | — | — | — | **Gap** (holidays not covered) | CR-008 |
| ADD-H-07 | Human escalation | M09, M04 | — | — | — | O8 | HLD only | CR-006 |
| ADD-H-08 | External integrations extend native workflows, not replace them | M11, M13 | — | — | — | — | HLD only | CR-008 |

## I. Inbound and Outbound Calling

| Req ID | Requirement | Modules | LLD tables | LLD APIs | Controls | Gate | Coverage | CR |
|---|---|---|---|---|---|---|---|---|
| ADD-I-01 | Inbound: number-to-tenant mapping, routing rules, business hours, agent selection | M06, M04, M02 | — | — | — | O2 | HLD only | CR-009 |
| ADD-I-02 | Inbound: welcome message, queue and fallback, human transfer | M06, M10 | — | — | — | O2, O8 | **Gap** (no queue design) | CR-009 |
| ADD-I-03 | Outbound: authorized campaign config, contact eligibility | M07 | — | — | HLD §7 policy gate | O3 | HLD only | CR-009 |
| ADD-I-04 | Outbound: consent and suppression checks | M07, M22 | `consent_records` | `POST /v1/consents` | LLD §8 | O3 | Partial (consent table exists; no suppression/DNC table) | CR-009 |
| ADD-I-05 | Outbound: calling windows, country restrictions | M07, M02 | — | — | HLD §7 India/USA; IANA tz | O3 | HLD only | CR-009 |
| ADD-I-06 | Outbound: rate/concurrency limits, retries, opt-out, outcome tracking, audit | M07, M15 | — | — | — | O3, O11 | HLD only | CR-009 |
| ADD-I-07 | No unrestricted bulk calling; meet telecom/privacy/consent/marketing rules | M07, M17 | — | — | HLD §7 (fail closed) | O3 | HLD only | CR-009 |

## J. Worker and Queue Architecture

| Req ID | Requirement | Modules | LLD tables | LLD APIs | Controls | Gate | Coverage | CR |
|---|---|---|---|---|---|---|---|---|
| ADD-J-01 | Control plane separate from real-time voice | M10 | — | — | HLD §1, §3 | — | HLD only | CR-010 |
| ADD-J-02 | Modular monolith control plane | All control-plane modules | — | — | HLD §10 decisions | — | HLD only | — (no gap) |
| ADD-J-03 | Independently deployable LiveKit voice workers, plus background workers | M10, M18 | — | — | LLD §13 (separate worker pool for healthcare) | — | HLD only | CR-010 |
| ADD-J-04 | Redis-backed queues | M10, M07, M14 | — | — | HLD v1.3 §4 Redis ACLs, tenant keys | — | HLD only | CR-010 |
| ADD-J-05 | Health checks, heartbeats, graceful shutdown, recovery | M10, M18 | — | — | HLD §8 | O14 | Partial (no heartbeat/recovery spec) | CR-010 |
| ADD-J-06 | Job retry, dead-letter queue, concurrency limits, backpressure | M10, M18 | — | — | — | O14 | **Gap** | CR-010 |
| ADD-J-07 | Regional voice workers (India, US) | M10, M02 | — | — | HLD §1 (regional SIP ≠ residency) | — | HLD only | CR-010 |
| ADD-J-08 | No premature Kubernetes | — | — | — | HLD §8, §10 | — | Covered (HLD decision) | — |

## K. Recording, Transcription and Consent

| Req ID | Requirement | Modules | LLD tables | LLD APIs | Controls | Gate | Coverage | CR |
|---|---|---|---|---|---|---|---|---|
| ADD-K-01 | Recording on/off per tenant **and per agent** | M22, M05, M08 | `consent_records` | — | LLD §8 | O13 | Partial (per-agent setting not modelled) | CR-011 |
| ADD-K-02 | Consent announcement and capture | M22, M10 | `consent_records` | `POST /v1/consents` | LLD §8 state machine | O13, HC-008 | Covered | — |
| ADD-K-03 | Recording access permissions | M22, M01 | — | `POST /v1/recordings/{id}/access-check` | LLD §5 | O13, HC-004, HC-006 | Covered | — |
| ADD-K-04 | Secure private storage and encryption | M08, M18 | `encryption_key_references` | — | LLD §3 ProtectedStorageService, §13 | O13 | Covered (healthcare); HLD only for standard tenants | CR-011 |
| ADD-K-05 | Retention schedules and deletion workflows | M24 | `healthcare_retention_policies` | `POST /v1/retention/requests` | LLD §10 | O13, HC-009 | Covered (healthcare); HLD only for standard tenants | CR-011 |
| ADD-K-06 | Recording access audit | M23 | `phi_access_audit_logs` | `GET /v1/audit/phi-access` | LLD §9 | O13 | Covered (healthcare); standard tenants not covered | CR-011 |
| ADD-K-07 | Transcript redaction and data minimization | M20, M08 | `phi_data_classifications` | — | LLD §3 PHIClassificationService | HC-007 | Covered (healthcare) | CR-011 |
| ADD-K-08 | Respect country/state/customer law | M22, M17 | `healthcare_policies` | — | LLD §8 legal-review note | O13 | Partial | CR-011 |
| ADD-K-09 | Healthcare tenants follow M19–M25 gates | M19–M25 | all LLD v1.3 tables | all LLD v1.3 APIs | LLD §6 activation gate | HC-001…HC-012 | Covered | — |

## L. Failover and Reliability

| Req ID | Requirement | Modules | LLD tables | LLD APIs | Controls | Gate | Coverage | CR |
|---|---|---|---|---|---|---|---|---|
| ADD-L-01 | STT / LLM / TTS provider fallback | M03, M09 | `vendor_compliance_records` | — | LLD §7 (fallback passes same checks) | O9, HC-010 | Partial (healthcare rule only) | CR-012 |
| ADD-L-02 | Telephony routing fallback | M04 | — | — | — | O9 | **Gap** | CR-012 |
| ADD-L-03 | Circuit breakers, exponential backoff with jitter, timeouts, retry limits | M03, M04, M09 | — | — | HLD §8 | O9 | HLD only | CR-012 |
| ADD-L-04 | Idempotency; never retry a consequential action without checking execution status | M09, M11, M15 | — | — | LLD §5 idempotency keys (healthcare cmds); HLD §8 | O10 | Partial | CR-007, CR-012 |
| ADD-L-05 | Graceful degradation, call failure handling, human fallback | M09, M10 | — | — | LLD §8 ERROR/UNKNOWN fail-safe (recording only) | O8, O9 | Partial | CR-012 |

## M. Concurrency and Capacity Management

| Req ID | Requirement | Modules | LLD tables | LLD APIs | Controls | Gate | Coverage | CR |
|---|---|---|---|---|---|---|---|---|
| ADD-M-01 | Tenant, plan and platform concurrent-call limits | M15, M02, M10 | — | — | — | O11 | **Gap** | CR-013 |
| ADD-M-02 | Provider rate limits | M03, M04 | — | — | — | O11 | **Gap** | CR-013 |
| ADD-M-03 | Worker capacity tracking, queue depth monitoring | M10, M18 | — | — | HLD §8 metrics | O11 | HLD only | CR-013 |
| ADD-M-04 | Admission control and overload protection | M10, M06, M07 | — | — | — | O11 | **Gap** | CR-013 |
| ADD-M-05 | Usage and spending limits | M15 | — | — | HLD §5 ceilings; LLD §14 | O11 | HLD only | CR-013 |
| ADD-M-06 | Capacity metrics: active/queued calls, utilization, provider usage, failure rates | M18, M16 | — | — | LLD §14 | O11 | HLD only | CR-014 |

## N. Observability and Operational Monitoring

| Req ID | Requirement | Modules | LLD tables | LLD APIs | Controls | Gate | Coverage | CR |
|---|---|---|---|---|---|---|---|---|
| ADD-N-01 | Trace each call across provider, SIP, LiveKit room, worker, STT, LLM, tool, TTS, billing | M18 | `phi_access_audit_logs.correlation_id` | — | LLD §7 (log provider ID, usage, correlation ID) | O15 | Partial (no span model) | CR-014 |
| ADD-N-02 | Correlation IDs and distributed tracing | M18 | — | — | LLD §14 OpenTelemetry | — | Covered (technology choice) | CR-014 (span spec) |
| ADD-N-03 | The 14 listed monitoring signals | M18, M16 | — | — | HLD §8, LLD §14 | O15 | Partial (transfer success, call quality, cost/minute not specified) | CR-014 |
| ADD-N-04 | Don't log secrets or sensitive conversation data | M18, M20 | — | — | LLD §14, §13; HC-007 | O16 | Covered | — |

## O. Architecture Performance and Acceptance Gates

| Gate | Gate statement | Verifies | LLD test | Coverage | CR |
|---|---|---|---|---|---|
| O1 | Browser voice end to end | ADD-A-03, ADD-B-* | — | **Gap** | CR-002, CR-015 |
| O2 | Inbound telephone end to end | ADD-A-04, ADD-I-01/02 | — | HLD §10 launch checklist only | CR-015 |
| O3 | Outbound telephone with consent controls | ADD-I-03…07 | — | HLD §10 only | CR-015 |
| O4 | Partial transcripts and streaming audio | ADD-B-02/03 | — | **Gap** | CR-015 |
| O5 | Barge-in | ADD-B-07/08 | — | **Gap** | CR-015 |
| O6 | RAG retrieves only authorized tenant data | ADD-G-01/03 | HC-004, HC-005 (adjacent) | Partial | CR-015 |
| O7 | Tools run only with valid permissions | ADD-G-02…06 | — | **Gap** | CR-015 |
| O8 | Human transfer and escalation | ADD-F-05, ADD-H-07 | — | HLD §10 only | CR-015 |
| O9 | Provider failure doesn't corrupt call state | ADD-E-01, ADD-L-* | HC-010 (adjacent) | Partial | CR-015 |
| O10 | Duplicate webhooks don't duplicate actions or billing | ADD-E-03, ADD-D-10 | — | **Gap** | CR-015 |
| O11 | Tenant concurrency and platform limits enforced | ADD-M-* | — | **Gap** | CR-015 |
| O12 | Usage recorded in actual provider units | ADD-D-13, ADD-E-02 | — | HLD §10 only | CR-015 |
| O13 | Recordings follow consent and retention policy | ADD-K-* | HC-008, HC-009 | Covered (healthcare) | CR-015 (standard tenants) |
| O14 | Voice workers recover from failures | ADD-J-05/06 | — | **Gap** | CR-015 |
| O15 | Latency measured and reported | ADD-C-* | — | **Gap** | CR-004, CR-015 |
| O16 | Critical tenant-isolation and security tests pass | ADD-G-06, ADD-N-04 | HC-001…HC-012 | Covered (healthcare) | CR-015 (core platform) |

## P. Module-Wise Vertical-Slice Delivery

| Req ID | Requirement | Modules | Coverage | CR / plan step |
|---|---|---|---|---|
| ADD-P-01 | Each module delivered as a full vertical slice (14 required elements) | All | **Gap**: no definition of done in LLD; Governance Handbook SOP-007/009 is related | CR-017; plan step 2 |
| ADD-P-02 | Module dependency graph | All | Partial (LLD v1.3 §2 dependencies for M19–M25 only) | CR-017; plan step 2 |
| ADD-P-03 | Implementation status register | All | **Gap** | CR-017; plan step 2 |
| ADD-P-04 | No dependent module starts before its acceptance gates pass | All | **Gap** | CR-017; plan step 2 |

## Q. Country and Language Configuration

| Req ID | Requirement | Modules | LLD tables | Controls | Coverage | CR |
|---|---|---|---|---|---|---|
| ADD-Q-01 | Markets India and US | M02 | `healthcare_tenant_profiles.jurisdiction` | HLD §2 | Covered (HLD) | — |
| ADD-Q-02 | Hindi, **Hinglish**, Indian English, US English | M02, M03, M09 | — | HLD §2 lists Hindi and Indian English (India), English (US) | **Gap**: Hinglish (code-switching) isn't a declared language | CR-016 |
| ADD-Q-03 | Country, currency, timezone, number format, carrier, language, consent and regulatory policy configurable | M02, M04, M22 | `healthcare_policies` (healthcare) | HLD §2 language registry | HLD only | CR-016 |
| ADD-Q-04 | INR and USD | M15, M02 | — | HLD §2 | HLD only | CR-016 |
| ADD-Q-05 | UTC internally, tenant IANA tz for business ops | All | all tables (LLD §4 rule) | LLD §4 | Covered | — |
| ADD-Q-06 | E.164 phone numbers | M04, M13, M07 | — | HLD §6 | Covered (HLD rule) | — |

## R. Non-Negotiable Architecture Constraints

| Req ID | Constraint | Where enforced | Coverage | CR |
|---|---|---|---|---|
| ADD-R-01 | Follow the approved HLD and LLD | Governance Handbook SOP-009, SOP-020 | Covered, but needs the M01–M18 baseline | CR-001 |
| ADD-R-02 | One common voice engine for all channels | M09, M10 | Gap (see A) | CR-002 |
| ADD-R-03 | Several SIP providers through adapters | M04 | HLD only | CR-005 |
| ADD-R-04 | Hybrid cloud and open-source AI | M03 | HLD §5 hybrid AI policy | — |
| ADD-R-05 | Tenant isolation at every data and execution boundary | M02, all | LLD §4 schema rules, HC-004/005 | Covered (rules); needs core tables (CR-001) |
| ADD-R-06 | Modular monolith control plane | — | HLD decision | — |
| ADD-R-07 | Independently deployable voice workers | M10 | HLD decision | CR-010 |
| ADD-R-08 | Docker on Ubuntu VPS at first | M18 | HLD §9 | — |
| ADD-R-09 | No unnecessary microservices or premature Kubernetes | — | HLD decision | — |
| ADD-R-10 | No real PHI in development | M19, M20 | HLD v1.3 §2, §8 | — |
| ADD-R-11 | No unapproved PHI transmission | M19, M21, M03 | LLD §6, §7, HC-002, HC-010 | — |
| ADD-R-12 | No unsupported HIPAA claims | M25 | LLD cover statement | — |
| ADD-R-13 | No fake integrations or made-up provider capabilities | M03, M04 | Capability registry needed | CR-005 |
| ADD-R-14 | No production-readiness claims without acceptance evidence | M25 | LLD §16 release checklist | CR-015 |

---

## Coverage summary

| Coverage | Count |
|---|---|
| Covered (LLD spec or explicit HLD rule) | 17 |
| Settled HLD decision, no gap (e.g. modular monolith, no Kubernetes, Docker on Ubuntu) | 10 |
| Partial | 23 |
| HLD only (no LLD detail) | 59 |
| Gap (in neither) | 34 |
| **Total rows** | **143** |

Counts include the 16 section O gates and were tallied from the tables above. Every row that isn't Covered points to at least one CR.
