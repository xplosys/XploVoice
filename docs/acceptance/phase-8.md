# Phase 8 acceptance report: Healthcare Mode

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Scope: LLD v1.3 M19 healthcare activation and policy, M20 PHI inventory and redaction, M21 vendor BAAs and
eligibility, M22 recording consent in healthcare, M23 PHI access log and incidents, M24 retention, legal holds and
rights requests, M25 control tests, evidence and risks; the privacy officer role; web screens and the admin console.

Data used is synthetic only, with no real patient data. The mock AI provider was marked PHI-eligible with a synthetic
BAA for the walkthrough. This report does not claim HIPAA compliance or production readiness.

## LLD v1.3 healthcare modules

| Module | Requirement | Evidence |
|---|---|---|
| M19 | Off by default; activation gate; four-eyes; versioned policy | `test_healthcare_mode_is_off_by_default_and_changes_nothing`, `test_request_needs_us_two_factor_and_synthetic_data`, `test_activation_gate_and_four_eyes`, `test_gate_names_what_is_missing`, `test_policy_versions_need_a_second_person` |
| M20 | PHI inventory, redaction, minimization | `test_redaction_masks_identifiers_and_minimize_keeps_only_ids`, `test_audit_log_phi_log_and_webhooks_hold_no_phi` |
| M21 | PHI only to vendors with a BAA in force, including fallback | `test_phi_goes_only_to_providers_with_a_baa_in_force_including_fallback`, `test_expired_vendor_baa_is_skipped` |
| M22 | Recording needs consent, a PHI role and the policy; guardrail and notice on every agent | `test_recording_needs_consent_a_phi_role_and_the_policy`, `test_every_agent_gets_the_guardrail_and_the_privacy_notice` |
| M23 | PHI withheld without phi:read; every access logged; incidents and notices | `test_phi_is_withheld_without_phi_read_and_every_access_is_logged`, `test_incident_assessment_schedules_the_right_notices`, `test_notification_plan_for_large_breaches_and_business_associates` |
| M24 | Retention purge except under legal hold; rights requests | `test_retention_purges_old_call_content_except_under_legal_hold`, `test_rights_requests_are_decided_by_a_second_person_exported_and_deleted` |
| M25 | Control tests, evidence, risk register, report | `test_control_tests_evidence_and_report`, `test_a_failing_control_test_blocks_activation` |
| Roles | Privacy officer; suspension keeps protections | `test_privacy_officer_role`, `test_suspension_stops_new_calls_but_keeps_every_protection` |

## Definition of done (master prompt §29)

| Criterion | Evidence |
|---|---|
| Migrations | `0008_healthcare` upgrades, downgrades to base and upgrades again |
| Automated tests | 205 API tests pass, 20 of them new; ruff, web typecheck, lint and build are clean |
| Authorization | New permissions healthcare:read/manage, phi:read, phi_audit:read, incidents:report/manage, retention:manage, evidence:manage; activation, BAAs, vendors and control tests are platform admin only with two-factor and a reason |
| Tenant isolation | FORCE RLS on every new tenant table; platform evidence rows have no tenant and only the platform writes BAA and control-test evidence |
| Audit | Requests, activation, suspension, policies, classifications, vendors, BAAs, incidents, holds, purges, rights decisions, evidence; PHI reads in the append-only PHI access log |
| Reliability | Purges run in a savepoint and refuse held calls in the database; deletion requests purge all or nothing |
| Documentation | ADR-0011, module register, CR-011 updated, test cases `phase-8-test-cases.md`, local development guide |

## Browser walkthrough

Checked in Chromium at Asia/Kolkata time with a synthetic clinic: the Healthcare page before asking and with the
gate passed; the admin activation console; the page once active; the team page with a privacy officer; the same call
as a viewer (transcript and number hidden) and as an operator; the PHI access log; an incident with its assessment
and notice dates; retention with a legal hold and rights requests; compliance evidence, risks and report; and the
admin console after activation. Screenshots are in the project's demo folder for Phase 8.

## Not done in Phase 8 (later phases or awaiting configuration)

- Real activation: needs a signed customer BAA, signed vendor BAAs, a production security review and legal sign-off.
- Recording storage (recordings are not stored yet, so the access check guards a future download).
- Encrypted backups with their own retention, break-glass access and automatic sending of breach notices.
