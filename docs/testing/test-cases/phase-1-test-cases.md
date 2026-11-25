# XploVoice test cases: Phase 1: platform foundation

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Synthetic data only. No PHI. Each automated case names the pytest test that checks it (`apps/api/tests`); manual cases are run in the browser.

33 test cases.

| ID | Area | Test case | Preconditions | Steps | Expected result | Type / automated test |
|---|---|---|---|---|---|---|
| TC-P1-01 | Sign-up | Register an organisation in India | None | Register with country IN | Owner created; INR, Asia/Kolkata, Indian languages set | Auto: test_identity::test_register_creates_owner_with_country_defaults |
| TC-P1-02 | Sign-up | Reject weak password | None | Register with a short, common password | Rejected with a clear message | Auto: test_weak_password_rejected |
| TC-P1-03 | Sign-up | Password stored as Argon2id | User registered | Inspect the stored hash | Hash is Argon2id, never plain text | Auto: test_password_is_argon2id |
| TC-P1-04 | Sign-in | Correct and wrong password | User registered | Sign in correctly, then with a wrong password | Token issued; wrong password gets 401 | Auto: test_login_and_wrong_password |
| TC-P1-05 | Sign-in | Lockout after repeated failures | User registered | Fail sign-in repeatedly | Account locked out | Auto: test_lockout_after_repeated_failures |
| TC-P1-06 | Sessions | Refresh rotation and reuse detection | Signed in | Refresh; reuse the old refresh token | Rotation works; reuse revokes the session | Auto: test_refresh_rotation_and_reuse_detection |
| TC-P1-07 | Sessions | Sign out ends access at once | Signed in | Sign out; call an API with the old token | 401 | Auto: test_logout_revokes_access_immediately |
| TC-P1-08 | Sessions | Tampered token rejected | Signed in | Alter the token and call the API | 401 | Auto: test_tampered_token_rejected |
| TC-P1-09 | Sessions | Password change ends other sessions | Two sessions | Change password in one | The other session gets 401 | Auto: test_password_change_revokes_sessions |
| TC-P1-10 | Sessions | Password change in a two-organisation account | Member of two organisations | Change password | Sessions end in every organisation | Auto: test_password_change_revokes_sessions_in_every_org |
| TC-P1-11 | 2FA | Enrol and sign in with an authenticator code | Signed in | Enrol TOTP, sign out, sign in with code | Code required and accepted | Auto: test_mfa_enroll_and_login; Manual: Security page |
| TC-P1-12 | 2FA | 2FA secret encrypted at rest | 2FA enrolled | Inspect the database | Secret is encrypted | Auto: test_mfa_secret_encrypted_at_rest |
| TC-P1-13 | Organisation | Validate time zone, language and phone | Owner signed in | Save bad values, then a valid phone | Bad values rejected; phone stored as E.164 | Auto: test_regional_settings_validation |
| TC-P1-14 | Organisation | Country reference data | None | Read countries | India: Hindi, Hinglish, Indian English; US: USD | Auto: test_reference_countries |
| TC-P1-15 | Team | Invite and join as viewer | Owner signed in | Invite, accept as a new user | Viewer joins the right organisation | Auto: test_invitation_flow_and_roles; Manual: Team page |
| TC-P1-16 | Team | Viewer cannot manage; denial audited | Viewer member | Viewer invites or renames | 403; each denial in the audit log | Auto: test_viewer_cannot_manage_and_denial_is_audited |
| TC-P1-17 | Team | Role rank and last-owner guards | Owner and admin | Admin promotes to owner; owner demotes self | 403 and 409 | Auto: test_role_rank_and_last_owner_guards |
| TC-P1-18 | Team | Role change ends sessions | Admin member signed in | Owner changes their role | Member's session gets 401 | Auto: test_role_change_ends_member_sessions |
| TC-P1-19 | Team | Invite for another email | Two accounts | Accept an invite meant for a different email | 403 | Auto: test_invitation_email_must_match_existing_account |
| TC-P1-20 | Team | Join a second organisation and switch | Two organisations | Accept invite; switch; switch to a non-member organisation | Switch works; non-member switch fails | Auto: test_existing_user_joins_second_org_and_switches |
| TC-P1-21 | Team | Invite link single use | Invite sent | Accept twice | Second use returns 404 | Auto: test_invitation_token_single_use |
| TC-P1-22 | Isolation | Runtime role cannot bypass row security | Database up | Check role flags | Not superuser, no BYPASSRLS | Auto: test_runtime_role_cannot_bypass_rls |
| TC-P1-23 | Isolation | Every tenant table has forced row security | Migrated | List tenant tables | All have ENABLE and FORCE RLS | Auto: test_every_tenant_table_has_forced_rls |
| TC-P1-24 | Isolation | SQL sees only the current tenant | Two tenants | Query and write as tenant A | Sees only A; write into B refused | Auto: test_sql_level_isolation |
| TC-P1-25 | Isolation | No tenant context sees nothing | Data exists | Query without context | Zero rows | Auto: test_no_context_sees_nothing |
| TC-P1-26 | Isolation | Another tenant's ids return 404 | Two tenants | Use B's member and invite ids as A | 404 | Auto: test_api_cannot_reach_other_tenant_resources |
| TC-P1-27 | Isolation | Member of two organisations sees only the current one | Two memberships | List members | Only current organisation | Auto: test_member_of_two_orgs_sees_only_current_org |
| TC-P1-28 | Isolation | Tenant id in request body ignored | Two tenants | Send B's id while renaming as A | A renamed; B untouched | Auto: test_tenant_id_in_body_is_ignored |
| TC-P1-29 | Isolation | Cannot end another user's sessions | Two users | Call revoke for the other user | Nothing revoked | Auto: test_revoke_my_sessions_cannot_target_another_user |
| TC-P1-30 | Audit | Audit log is append-only | Audit rows exist | Update or delete as the app role | Permission denied | Auto: test_audit_log_is_append_only_for_runtime_role |
| TC-P1-31 | Audit | Audit hash chain links | Events recorded | Read the chain | Each row links to the previous | Auto: test_audit_hash_chain_links |
| TC-P1-32 | Audit | No secrets in audit | Sign-in, 2FA, password events | Inspect audit metadata | No passwords, tokens or codes | Auto: test_audit_never_contains_secrets |
| TC-P1-33 | Admin | Platform admin needs flag and 2FA; suspension | Staff and customer accounts | Open admin without flag, without 2FA, then suspend customer | 403, 403, then allowed; customer sessions end and sign-in blocked | Auto: test_platform_admin_requires_flag_and_mfa; Manual: admin console |
