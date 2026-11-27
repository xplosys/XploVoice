# ADR-0011: Healthcare Mode (US, HIPAA-aligned controls)

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys · Status: accepted for development

**Context.** Phase 8 builds the healthcare modules M19–M25 from LLD v1.3. Healthcare Mode is for US covered entities
and business associates. It must keep PHI away from vendors without a business associate agreement (BAA), limit who
sees PHI, log every look at it, keep agents to administrative tasks, and give the organisation retention, incident
and evidence tools. XploVoice gives no legal advice and makes no compliance claim: it records evidence and enforces
technical controls.

**Decision.**

**Activation (M19)**
- Off by default for every organisation and on the platform (`XV_HEALTHCARE_ENABLED=false`). An owner or admin
  with two-factor asks for it (status *requested*); outside production they must attest that only synthetic data is
  used. Only a platform admin can activate, and never the same person who asked.
- Activation passes only when all 11 gate checks pass: platform enabled, requested, US jurisdiction, synthetic data
  outside production, customer BAA on file and in date, an approved healthcare policy, retention set, a privacy
  officer, two-factor for every member who can see PHI, a BAA-covered provider for LLM, STT and TTS, and passing
  control tests from the last 30 days.
- Healthcare policies are versioned; a second person approves each version. Until one is approved the strictest
  settings apply (no recording, no outbound campaigns).
- Suspension refuses new calls (`healthcare_suspended`) and keeps every protection on. Withdrawal is allowed only
  before activation.

**PHI handling (M20, M22, M23)**
- A PHI inventory per organisation; calls, transcripts, recordings and rights requests are locked as PHI.
- Without `phi:read` (viewer, agent designer) transcripts and the caller's number are hidden and numbers are masked
  (`+1••••••0123`). Every view of a call, recording access check and export writes an append-only
  `phi_access_audit_logs` row (who, what, allowed or not, purpose), never the PHI itself.
- Webhook payloads are minimized to ids and safe fields; incident text is redacted before it is stored.
- Recordings need the policy, recorded caller consent and `phi:read`.
- Every agent gets the administrative-only guardrail (no diagnosis, prescribing or triage) and the privacy notice
  before its greeting.

**Vendors (M21)**
- `vendor_compliance_records` are platform data, append-only: the latest row is the BAA status. A provider must be
  marked PHI-eligible *and* have a signed, unexpired BAA. Routing considers only those, including for fallback;
  customer-owned keys are not used, because XploVoice cannot see that agreement.

**Incidents (M23)**
- Anyone can report. A privacy officer (or owner or admin) records the four-factor risk assessment. A breach
  schedules notices: individuals within 60 days of discovery; HHS within 60 days for 500 or more people, otherwise
  within 60 days after the year ends; media for 500 or more in a state; a business associate notifies the covered
  entity. Dates are for tracking only.

**Retention and rights (M24)**
- Retention days per kind of content. A purge (definer function `purge_call_content`) removes transcripts, event
  details, tool inputs and the other party's number, keeps the call row for billing and audit, and refuses calls
  under a legal hold. Rights requests (access, amendment, deletion, accounting) are decided by a second person.

**Evidence (M25)**
- Control tests check forced RLS, the runtime role, append-only tables, the purge guard, PHI vendors and secrets,
  and save their result with the commit and environment. Evidence (risk analysis, training, BAAs) and a risk register
  feed a compliance report.

**New role.** `privacy_officer` (rank 2): healthcare, PHI read, PHI log, incidents, retention and evidence; no agent,
billing or team management.

**Consequences.**
- Turning Healthcare Mode on is an operational act with evidence behind it, not a switch.
- Real activation still needs a signed customer BAA, signed vendor BAAs, a production security review and legal
  sign-off. None of this is claimed here.
- Recording storage, encrypted backups with their own retention, and break-glass access are not built yet.
