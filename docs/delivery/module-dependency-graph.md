# Module Dependency Graph

| Field | Value |
|---|---|
| Source | Addendum §P (ADD-P-02), CR-017; LLD v1.3 §2 for M19–M25 |
| Module IDs | [Module catalogue](../architecture/module-catalogue.md). M01–M18 are provisional (CR-001) |
| Status | Draft |

**Hard** dependency: the module can't pass *Design* until the dependency is Done.
**Soft** dependency: work can start, but the feature that needs it stays off until the dependency is Done.
For M19–M25, the dependencies are exactly as LLD v1.3 states them.

## Graph

```mermaid
graph LR
  M01[M01 Identity] --> M02[M02 Tenant]
  M02 --> M17[M17 Super Admin & Compliance]
  M01 --> M17
  M02 --> M18[M18 Observability]

  M02 --> M03[M03 Provider Registry / AI Gateway]
  M17 --> M03
  M02 --> M08[M08 Conversation & Recordings]
  M18 --> M08
  M03 --> M05[M05 Agent Mgmt]
  M02 --> M05

  M03 --> M09[M09 AI Orchestration]
  M05 --> M09
  M08 --> M09
  M09 --> M10[M10 Voice Runtime & Workers]
  M18 --> M10

  M03 --> M04[M04 Telephony]
  M17 --> M04
  M04 --> M06[M06 Inbound Calls]
  M10 --> M06
  M05 --> M06

  M03 --> M12[M12 Knowledge Base]
  M02 --> M11[M11 Appointments]
  M02 --> M13[M13 CRM & Leads]
  M02 --> M14[M14 Notifications]

  M03 --> M15[M15 Usage & Billing]
  M04 --> M15
  M08 --> M15
  M08 --> M16[M16 Analytics]
  M15 --> M16

  M04 --> M22[M22 Consent & Recording]
  M08 --> M22
  M10 --> M22
  M22 --> M07[M07 Outbound Campaigns]
  M04 --> M07
  M10 --> M07
  M13 --> M07
  M14 --> M07
  M15 --> M07

  M01 --> M19[M19 Healthcare]
  M02 --> M19
  M17 --> M19
  M03 --> M20[M20 PHI Classification]
  M08 --> M20
  M12 --> M20
  M03 --> M21[M21 BAA & Vendor]
  M04 --> M21
  M17 --> M21
  M01 --> M23[M23 Audit & Breach]
  M02 --> M23
  M08 --> M23
  M17 --> M23
  M08 --> M24[M24 Retention & Rights]
  M12 --> M24
  M13 --> M24
  M17 --> M25[M25 Compliance Evidence]
  M18 --> M25
```

Soft dependencies (not drawn): M05 → M12 (KB bindings) and M05 → M09 (tool grants); M10 → M04 (SIP channel);
M09 → M11/M13/M14 (business tools); M06 → M11 (business hours/holidays).

## Cycle found in the LLD: M07 ↔ M22

LLD v1.3 lists **M22 Consent & Recording depends on M07 Outbound Campaigns**, but outbound campaigns can't
run without consent checks (ADD-I-04), so M07 depends on M22. That's a cycle.

**Proposed fix (part of CR-011):** split it in two.

- **M22-core:** consent records, notice playback and recording modes for all tenants. It depends on M04, M08 and M10, and it's built before M07.
- **M22-outbound:** campaign-specific consent evidence and suppression links. It's built together with M07.

The graph above shows the proposed order (M22 before M07). It needs approval before M07 starts.

## Build waves

| Wave | Modules | Exit gates (addendum §O / LLD §12) | Plan step |
|---|---|---|---|
| W0 Foundation | M01, M02, M17 (audit core), M18 (CI, logging, tracing base) | O16 core isolation (API, SQL, RLS, jobs); secure login and tenant setup | Step 3 |
| W1 Voice core config | M03 (STT/LLM/TTS adapters + mocks), M05, M08 | Immutable agent versions; adapter contract tests | Step 4 |
| W2 Common voice engine (browser channel) | M09, M10 | O1, O4, O5, O14; O15 measured (target not yet claimed) | Step 4 |
| W3 Telephony and inbound | M04, M06, M12 | O2, O6, O8, O9, O10 | Later |
| W4 Business tools and billing | M11, M13, M14, M15 | O7, O10, O12 | Later |
| W5 Outbound and consent | M22-core, M07 (+ M22-outbound), M16 | O3, O11, O13 | Later |
| W6 Healthcare mode | M19, M20, M21, M23, M24, M25 | HC-001 … HC-012; LLD §16 release checklist | Later |

W3 can run in parallel with W2 once W1 is Done, because M04 doesn't depend on M09 or M10.
