# XploVoice test cases: Phase 8 (Healthcare Mode)

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Synthetic data only. No real patient data, ever. Use 555 numbers and made-up names. Run the API with
`XV_HEALTHCARE_ENABLED=true` for the manual cases. Each automated case names the pytest test that checks it
(`apps/api/tests/test_healthcare.py`); manual cases are run in the browser.

30 test cases.

| ID | Area | Test case | Preconditions | Steps | Expected result | Type / automated test |
|---|---|---|---|---|---|---|
| TC-P8-01 | Activation | Off by default and changes nothing | New organisation | Open the healthcare overview; make a call; send a webhook | Mode off; calls, transcripts and webhooks as before | Auto: test_healthcare_mode_is_off_by_default_and_changes_nothing |
| TC-P8-02 | Activation | Asking needs US, two-factor and the synthetic-data attestation | Owner without two-factor; Indian organisation | Ask without two-factor; ask from India; ask without the attestation | Refused each time with the reason; then accepted when all are met | Auto: test_request_needs_us_two_factor_and_synthetic_data |
| TC-P8-03 | Policy | Policy versions need a second person | Two members with healthcare rights | Write a version; approve it yourself; approve as the other person | Self-approval refused; second approval puts it in force; strictest settings before that | Auto: test_policy_versions_need_a_second_person |
| TC-P8-04 | Activation | Gate and four-eyes | Requested organisation with everything ready | Activate as the platform admin who asked; as another admin | Refused; then active | Auto: test_activation_gate_and_four_eyes |
| TC-P8-05 | Activation | Gate names what is missing | Requested organisation, nothing ready | Open the gate | Each failed check is named with what to do | Auto: test_gate_names_what_is_missing |
| TC-P8-06 | Vendors | PHI only to providers with a BAA, fallback included | Two providers, one with a BAA | Route an AI request in Healthcare Mode | Only the BAA provider is used, also as fallback; customer keys skipped | Auto: test_phi_goes_only_to_providers_with_a_baa_in_force_including_fallback |
| TC-P8-07 | Vendors | Expired vendor BAA is skipped | Vendor BAA past its expiry | Route a request | Provider not used; gate check fails | Auto: test_expired_vendor_baa_is_skipped |
| TC-P8-08 | PHI | PHI withheld without phi:read; every access logged | Active organisation; viewer and operator | Open a call as each | Viewer: transcript and number hidden; operator: shown; both views in the PHI log | Auto: test_phi_is_withheld_without_phi_read_and_every_access_is_logged |
| TC-P8-09 | PHI | Audit log, PHI log and webhooks hold no PHI | Call with a name and date of birth | Read the audit log, PHI log and webhook payload | Ids only, no names, numbers or dates | Auto: test_audit_log_phi_log_and_webhooks_hold_no_phi |
| TC-P8-10 | PHI | Redaction and minimization | None | Redact text with a phone, email and date; minimize a payload | Identifiers replaced; only safe keys kept | Auto: test_redaction_masks_identifiers_and_minimize_keeps_only_ids |
| TC-P8-11 | Recording | Needs consent, a PHI role and the policy | Policy with recording on consent | Check access without consent; as a viewer; with consent as an operator | Refused, refused, allowed; each logged | Auto: test_recording_needs_consent_a_phi_role_and_the_policy |
| TC-P8-12 | Agents | Guardrail and privacy notice on every agent | Active organisation with a notice | Start a call on any agent type | Administrative-only guardrail in the prompt; notice spoken before the greeting | Auto: test_every_agent_gets_the_guardrail_and_the_privacy_notice |
| TC-P8-13 | Retention | Purge old content except under a legal hold | Retention 30 days; two old calls, one held | Run retention | Unheld call content removed, call row kept; held call untouched | Auto: test_retention_purges_old_call_content_except_under_legal_hold |
| TC-P8-14 | Rights | Requests decided by a second person, exported and deleted | Access and deletion requests | Decide your own; decide as another; export; complete the deletion | Self-decision refused; export logged; content purged | Auto: test_rights_requests_are_decided_by_a_second_person_exported_and_deleted |
| TC-P8-15 | Incidents | Assessment schedules the right notices | Reported incident, 1 person | Record a not-low risk assessment | Notices to individuals and HHS with due dates | Auto: test_incident_assessment_schedules_the_right_notices |
| TC-P8-16 | Incidents | Large breaches and business associates | None | Plan for 600 people; for a business associate | Media and HHS within 60 days; covered entity notified | Auto: test_notification_plan_for_large_breaches_and_business_associates |
| TC-P8-17 | Evidence | Control tests, evidence and report | Platform admin | Run control tests; add evidence and risks; open the report | All pass with commit and environment; report lists evidence and risks | Auto: test_control_tests_evidence_and_report |
| TC-P8-18 | Evidence | A failing control test blocks activation | Failed control test run | Activate | Refused: control tests not passing | Auto: test_a_failing_control_test_blocks_activation |
| TC-P8-19 | Suspension | New calls stop, protections stay | Active organisation | Suspend; ring the number; open a call as a viewer | Call refused; PHI still hidden and logged | Auto: test_suspension_stops_new_calls_but_keeps_every_protection |
| TC-P8-20 | Roles | Privacy officer | Owner | Invite a privacy officer; try agent and billing changes | Healthcare, PHI log, incidents and retention allowed; others 403 | Auto: test_privacy_officer_role |
| TC-P8-21 | Web | Ask for Healthcare Mode | US owner with two-factor | Open Healthcare; fill the form | Profile shown; gate lists what is left | Manual: Healthcare page |
| TC-P8-22 | Web | Draft and approve a policy | Two members | Write a version; sign in as the other; approve | Draft shown with "someone else must approve"; then in force | Manual: Healthcare page |
| TC-P8-23 | Web | Admin activation console | Platform admin with two-factor | Record a BAA, a vendor BAA, run control tests, activate | Gate shows all passed; organisation active | Manual: Admin → Healthcare |
| TC-P8-24 | Web | Call as viewer and operator | Active organisation with a call | Open the call as each | Viewer sees the hidden notice and masked numbers; operator sees the transcript | Manual: Calls page |
| TC-P8-25 | Web | PHI access log | Calls viewed | Open Healthcare → PHI access log | Each view with person, purpose and allowed or refused | Manual: PHI access log |
| TC-P8-26 | Web | Report and assess an incident | Any member reports; privacy officer assesses | Report; assess; record a notice as sent; close | Notices with due dates; sent recorded; closed | Manual: Incidents |
| TC-P8-27 | Web | Retention, holds and rights requests | Privacy officer and owner | Set days; place a hold; log a request; decide as the other | Saved; hold listed; decision recorded | Manual: Retention |
| TC-P8-28 | Web | Compliance evidence and report | Privacy officer | Add evidence and a risk; open the report | Listed with score; report shows gate, controls and evidence | Manual: Compliance |
| TC-P8-29 | Web | Suspended notice | Suspended organisation | Open Healthcare | Suspended notice with the reason | Manual: Healthcare page |
| TC-P8-30 | Activation (gate) | Real activation for a real clinic | Signed BAAs, security review, legal sign-off | Activate in production | Not run: awaiting contracts and sign-off | Manual: not run |
