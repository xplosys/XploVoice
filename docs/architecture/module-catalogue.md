# XploVoice Module Catalogue

| Field | Value |
|---|---|
| Status | **Provisional for M01–M18** (see CR-001). M19–M25 are official (LLD v1.3 §2). |
| Sources | XploVoice HLD v1.0 §4, HLD v1.3, LLD v1.3 §2 |
| Date | 24 November 2026 |

## Why part of this is provisional

LLD v1.3 defines only the Healthcare modules **M19–M25**. Their dependency columns refer to
**M01–M18**, but none of the documents we have (HLD v1.0, HLD v1.3, LLD v1.3, the Governance
Handbook v1.0) define those IDs. LLD v1.0–v1.2 is not available.

To get on with the addendum mapping, this catalogue gives provisional IDs to the 15 functional
modules in HLD v1.0 §4. It adds three modules the HLD describes as platform components but doesn't
list as modules. The numbering was chosen so that **every dependency stated in LLD v1.3 §2 makes
sense** (see the check table below). When the official M01–M18 catalogue turns up, replace this
table and re-key the traceability matrix. CR-001 tracks this.

## Catalogue

| ID | Module | Responsibility (from HLD) | Owner | Status |
|---|---|---|---|---|
| M01 | Identity & Access | Registration, verification, login, refresh, MFA, RBAC/ABAC, API keys, OIDC SSO | FastAPI | Provisional |
| M02 | Tenant Management | Workspace, country, timezone, currency, plan, policies, users, RLS tenant context | FastAPI | Provisional |
| M03 | Provider Registry & AI Gateway | Provider catalogue, capability registry, STT/LLM/TTS/embedding adapters, routing, metering hooks | FastAPI + adapters | Provisional (added; HLD §5 "Provider abstraction", HLD v1.3 §4 "AI gateway") |
| M04 | Telephony | Telephony provider adapters, SIP trunks, numbers/DIDs, routing, webhook intake | FastAPI + adapters | Provisional |
| M05 | Agent Management | Agent types, prompts, voice, tools, immutable versions, test, publish, pause | FastAPI | Provisional |
| M06 | Inbound Calls | Number mapping, dispatch, session creation, inbound lifecycle | Voice plane | Provisional |
| M07 | Outbound Campaigns | Imports, consent validation, schedules, concurrency, retries, suppression | FastAPI + workers | Provisional |
| M08 | Conversation & Recordings | Call events, transcripts, summaries, outcomes, recordings | Voice plane + workers | Provisional |
| M09 | AI Orchestration | STT/LLM/TTS routing, VAD, RAG invocation, fallback, tool execution | Voice plane | Provisional |
| M10 | Voice Runtime & Workers | LiveKit SIP/Agents, voice worker sessions, audio ingress/egress, notice playback, worker lifecycle | Voice plane | Provisional (added; HLD §3 "Real-time voice" plane) |
| M11 | Appointments | Services, staff, hours, availability, booking, calendar sync | FastAPI | Provisional |
| M12 | Knowledge Base | Upload, extract, chunk, embed, retrieve, reindex (pgvector) | FastAPI + workers | Provisional |
| M13 | CRM & Leads | Contacts, qualification, tasks, external integrations | FastAPI | Provisional |
| M14 | Notifications | Email, SMS, WhatsApp, reminders | Workers | Provisional |
| M15 | Usage & Billing | Metering, provider cost ledger, plans, invoices, limits | FastAPI + workers | Provisional |
| M16 | Analytics | Call, campaign, agent, appointment and cost reporting | Read models/workers | Provisional |
| M17 | Super Admin & Compliance | Provider catalogue admin, tenant support, platform policies, audit, retention | Admin API | Provisional |
| M18 | Observability & Operations | Tracing, metrics, logs, alerts, health checks, runbooks, backup/restore | Platform | Provisional (added; HLD §8 "Observability") |
| M19 | Healthcare Compliance | Tenant healthcare profile, activation gates, policy versioning | — | **Official** (LLD v1.3) |
| M20 | PHI Classification | Data labels, field/resource classification, PHI minimization | — | **Official** |
| M21 | BAA & Vendor Governance | Vendor service registry, BAA evidence, allowlists, expiry | — | **Official** |
| M22 | Consent & Recording | Notices, consent state, recording mode, pause/resume, retention linkage | — | **Official** |
| M23 | Audit & Breach | PHI access audit, incident case, breach assessment, notification | — | **Official** |
| M24 | Retention & Rights | Retention schedules, legal hold, export/correction/deletion | — | **Official** |
| M25 | Compliance Evidence | Evidence inventory, risk register, control tests, reports | — | **Official** |

## Consistency check against LLD v1.3 dependencies

| Official module | Stated dependencies | Why the provisional IDs fit |
|---|---|---|
| M19 Healthcare Compliance | M01, M02, M17 | Identity, tenant, super-admin policy/audit |
| M20 PHI Classification | M03, M08, M12 | AI gateway (minimization before dispatch), transcripts/recordings, embeddings |
| M21 BAA & Vendor Governance | M03, M04, M17 | AI provider registry, telephony vendors, admin |
| M22 Consent & Recording | M04, M07, M08, M10 | Telephony, outbound consent, recordings, runtime plays notice |
| M23 Audit & Breach | M01, M02, M08, M17 | Actors, tenants, recordings/transcripts, admin audit |
| M24 Retention & Rights | M08, M12, M13 | Recordings/transcripts, embeddings, contact/patient records |
| M25 Compliance Evidence | M17, M18 | Admin/compliance, operational evidence (tests, restores, monitoring) |

## Dependency outline (provisional)

```
M01 ─┬─ M02 ─┬─ M03 ─┬─ M09 ─┬─ M10 ─┬─ M06
     │       │       │       │       └─ M07 (also M13, M14)
     │       ├─ M04 ─────────┘
     │       ├─ M05 (M03, M04, M12)
     │       ├─ M12 (M03)
     │       ├─ M11, M13, M14
     │       └─ M15 (M03, M04, M08) ── M16
     └─ M17 ── M18
M08 (M02, M10)
```

Step 2 of the plan turns this outline into the formal dependency graph and status register.
