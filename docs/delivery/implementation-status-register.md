# Implementation Status Register

| Field | Value |
|---|---|
| Source | Addendum §P (ADD-P-03), CR-017 |
| Updated | 25 November 2026 (IST) |
| How to update | Change a row in the same PR that moves a module forward. Link evidence for each DoD element ticked. |

Status values and rules are in the [definition of done](definition-of-done.md). Dependencies and waves are in the
[dependency graph](module-dependency-graph.md). **DoD** counts the 14 elements done for the module.

## Register

| ID | Module | Wave | Hard deps | Gates to pass | LLD section | Status | DoD | Blocker / notes |
|---|---|---|---|---|---|---|---|---|
| M01 | Identity & Access | W0 | — | O16 (authn/authz) | none, CR-001 | Not started | 0/14 | Core LLD missing (CR-001) |
| M02 | Tenant Management | W0 | M01 | O16 (RLS, server tenant context) | §4 schema rules | Not started | 0/14 | CR-001 |
| M17 | Super Admin & Compliance | W0 | M01, M02 | O16 (privileged path audited) | none, CR-001 | Not started | 0/14 | CR-001 |
| M18 | Observability & Operations | W0 | M02 | CI security gates (LLD §13) | §13, §14 | Not started | 0/14 | Span model CR-014 |
| M03 | Provider Registry & AI Gateway | W1 | M02, M17 | Adapter contract tests; O9 (part) | §7 | Not started | 0/14 | CR-012 |
| M05 | Agent Management | W1 | M02, M03 | Immutable versions | none, CR-006 | Not started | 0/14 | CR-006 |
| M08 | Conversation & Recordings | W1 | M02, M18 | O12 (part) | none, CR-003 | Not started | 0/14 | CR-003 |
| M09 | AI Orchestration | W2 | M03, M05, M08 | O1, O4, O5 | none, CR-002 | Not started | 0/14 | CR-002, CR-007 |
| M10 | Voice Runtime & Workers | W2 | M09, M18 | O1, O14, O15 | none, CR-002/010 | Not started | 0/14 | CR-002, CR-004, CR-010 |
| M04 | Telephony | W3 | M03, M17 | O2, O10 | none, CR-005 | Not started | 0/14 | Needs carrier sandbox access per market |
| M06 | Inbound Calls | W3 | M04, M05, M10 | O2, O8, O9 | none, CR-009 | Not started | 0/14 | CR-003, CR-009 |
| M12 | Knowledge Base | W3 | M02, M03 | O6 | none, CR-007 | Not started | 0/14 | CR-007 |
| M11 | Appointments | W4 | M02 | O7, O10 (race-safe booking) | none, CR-008 | Not started | 0/14 | CR-008 |
| M13 | CRM & Leads | W4 | M02 | O7 | none, CR-008 | Not started | 0/14 | CR-008 |
| M14 | Notifications | W4 | M02 | O10 (outbox idempotency) | none | Not started | 0/14 | CR-001 |
| M15 | Usage & Billing | W4 | M03, M04, M08 | O10, O11, O12 | §14 | Not started | 0/14 | CR-013 |
| M22 | Consent & Recording (core) | W5 | M04, M08, M10 | O13; HC-008 | §8 | Not started | 0/14 | M07↔M22 cycle, CR-011 |
| M07 | Outbound Campaigns | W5 | M04, M10, M13, M14, M15, M22 | O3, O11 | none, CR-009 | Not started | 0/14 | Legal/carrier confirmation per market |
| M16 | Analytics | W5 | M08, M15 | O15 reporting | none | Not started | 0/14 | CR-014 |
| M19 | Healthcare Compliance | W6 | M01, M02, M17 | HC-001, HC-003 | §2, §6 | Not started | 0/14 | BAAs required before real PHI |
| M20 | PHI Classification | W6 | M03, M08, M12 | HC-007 | §3 | Not started | 0/14 | — |
| M21 | BAA & Vendor Governance | W6 | M03, M04, M17 | HC-002, HC-003, HC-010 | §3, §7 | Not started | 0/14 | — |
| M23 | Audit & Breach | W6 | M01, M02, M08, M17 | HC-004, HC-006, HC-011 | §9, §11 | Not started | 0/14 | — |
| M24 | Retention & Rights | W6 | M08, M12, M13 | HC-009, HC-012 | §10 | Not started | 0/14 | — |
| M25 | Compliance Evidence | W6 | M17, M18 | LLD §16 checklist | §3 | Not started | 0/14 | — |

## Open blockers

| Blocker | Affects | Owner | Needed |
|---|---|---|---|
| CR-001: core LLD for M01–M18 missing | All W0–W5 | Tausif | Supply LLD v1.0–1.2 or approve provisional catalogue |
| CR-002 … CR-017 pending | See register | Tausif | Approve or amend |
| M07 ↔ M22 dependency cycle | M07, M22 | Tausif | Approve the M22 split (CR-011) |
| Carrier sandbox access (India, US) | M04, M06, M07 | Tausif | Pick a first carrier per market |
