# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 8: Healthcare Mode (LLD v1.3 modules M19-M25).

M19 healthcare compliance: the tenant healthcare profile (off until a platform admin activates it through the
activation gate), versioned healthcare policies with four-eyes approval, and the privacy officer role.
M20 PHI classification: the tenant's inventory of what holds PHI.
M21 BAA and vendor governance: append-only vendor BAA records; AI providers serve PHI only with a signed,
unexpired BAA on record.
M22 consent and recording: recording access checks (recording storage itself is awaiting configuration).
M23 audit and breach: an append-only PHI access log, security incidents, breach assessments and the
notifications they require (tracked here; XploVoice sends nothing).
M24 retention and rights: retention schedules, legal holds, patient rights requests and retention runs. Call
content is purged only by a narrow SECURITY DEFINER function that refuses calls under a legal hold.
M25 compliance evidence: an evidence inventory (customer BAAs, control-test runs, risk assessments), a risk
register.

All healthcare data in development and tests is synthetic. Nothing here is a claim of HIPAA compliance.

Revision ID: 0008_healthcare
Revises: 0007_billing
"""

from alembic import op

revision = "0008_healthcare"
down_revision = "0007_billing"
branch_labels = None
depends_on = None

ROLES_OLD = "'owner', 'admin', 'agent_designer', 'operator', 'viewer'"
ROLES_NEW = "'owner', 'admin', 'agent_designer', 'operator', 'viewer', 'privacy_officer'"

TENANT_TABLES = (
    "healthcare_tenant_profiles",
    "healthcare_policies",
    "phi_data_classifications",
    "phi_access_audit_logs",
    "security_incidents",
    "breach_assessments",
    "breach_notifications",
    "healthcare_retention_policies",
    "legal_holds",
    "retention_requests",
    "retention_runs",
    "compliance_risks",
)

UPGRADE = rf"""
-- ------------------------------------------------------------------ roles: the privacy officer (HLD v1.3 section 6)
alter table tenant_memberships drop constraint tenant_memberships_role_check;
alter table tenant_memberships add constraint tenant_memberships_role_check check (role in ({ROLES_NEW}));
alter table invitations drop constraint invitations_role_check;
alter table invitations add constraint invitations_role_check
  check (role in ('admin', 'agent_designer', 'operator', 'viewer', 'privacy_officer'));

-- ------------------------------------------------------------------ M19 healthcare compliance
-- No row: healthcare mode is off. 'requested' changes nothing yet. 'active' and 'suspended' both keep every PHI
-- protection on; 'suspended' also refuses new calls. Only a platform admin moves a profile to 'active', and never
-- the person who requested it.
create table healthcare_tenant_profiles (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null unique references tenants(id) on delete cascade,
  status text not null default 'requested' check (status in ('requested', 'active', 'suspended', 'withdrawn')),
  jurisdiction text not null check (jurisdiction in ('US')),
  entity_type text not null check (entity_type in ('covered_entity', 'business_associate')),
  privacy_contact text not null check (length(privacy_contact) between 3 and 200),
  synthetic_data_only boolean not null default true,
  requested_by_user_id uuid not null,
  requested_at timestamptz not null default now(),
  activated_by_user_id uuid,
  activated_at timestamptz,
  activation_reason text,
  gate_snapshot jsonb,
  suspended_at timestamptz,
  suspended_reason text,
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  check (activated_by_user_id is null or activated_by_user_id <> requested_by_user_id)
);

-- Versioned policy. A version is written by one member and approved by another; the latest approved version is
-- in force. Versions are never edited after approval.
create table healthcare_policies (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  version integer not null check (version >= 1),
  recording_mode text not null default 'off' check (recording_mode in ('off', 'consent_required')),
  privacy_notice text not null default '' check (length(privacy_notice) <= 400),
  allow_outbound_campaigns boolean not null default false,
  change_note text not null check (length(change_note) between 3 and 500),
  status text not null default 'draft' check (status in ('draft', 'approved', 'superseded')),
  created_by_membership_id uuid not null,
  created_at timestamptz not null default now(),
  approved_by_membership_id uuid,
  approved_at timestamptz,
  unique (tenant_id, version),
  check (approved_by_membership_id is null or approved_by_membership_id <> created_by_membership_id),
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);

-- ------------------------------------------------------------------ M20 PHI classification
create table phi_data_classifications (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  resource_type text not null check (resource_type ~ '^[a-z_]{{3,40}}$'),
  classification text not null check (classification in ('phi', 'review', 'not_phi')),
  locked boolean not null default false,
  note text not null default '',
  updated_by_membership_id uuid,
  updated_at timestamptz not null default now(),
  unique (tenant_id, resource_type),
  check (not locked or classification = 'phi')
);

-- ------------------------------------------------------------------ M21 BAA and vendor governance (platform data)
-- Append-only: the latest record for a vendor is its current state. Terminating a BAA is a new record.
create table vendor_compliance_records (
  id uuid primary key default gen_random_uuid(),
  vendor_type text not null check (vendor_type in ('ai_provider', 'telephony', 'hosting', 'other')),
  vendor_key text not null check (vendor_key ~ '^[a-z0-9_-]{{2,60}}$'),
  vendor_name text not null check (length(vendor_name) between 2 and 120),
  services text not null default '',
  baa_status text not null check (baa_status in ('signed', 'terminated')),
  signed_on date,
  expires_on date,
  reference text not null check (length(reference) between 3 and 300),
  notes text not null default '',
  recorded_by uuid,
  created_at timestamptz not null default now(),
  check (baa_status <> 'signed' or signed_on is not null),
  check (expires_on is null or signed_on is null or expires_on > signed_on)
);
create index on vendor_compliance_records (vendor_type, vendor_key, created_at desc);

-- ------------------------------------------------------------------ M23 audit and breach
-- Append-only for the runtime role. Never holds PHI itself: ids, actions and purposes only.
create table phi_access_audit_logs (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  actor_user_id uuid,
  actor_kind text not null default 'user' check (actor_kind in ('user', 'platform_admin', 'system')),
  action text not null check (action in ('view', 'list', 'export', 'access_check', 'purge', 'amend')),
  resource_type text not null,
  resource_id text,
  purpose text not null default '',
  result text not null check (result in ('allowed', 'denied')),
  reason text,
  correlation_id text,
  ip_hash text,
  occurred_at timestamptz not null default now()
);
create index on phi_access_audit_logs (tenant_id, occurred_at desc);

create table security_incidents (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  title text not null check (length(title) between 3 and 200),
  summary text not null default '' check (length(summary) <= 4000),
  category text not null check (category in ('unauthorized_access', 'misdirected_communication', 'lost_device',
    'vendor_incident', 'system_vulnerability', 'other')),
  severity text not null check (severity in ('low', 'medium', 'high', 'critical')),
  status text not null default 'open' check (status in ('open', 'assessing', 'notifying', 'closed')),
  phi_involved text not null default 'unknown' check (phi_involved in ('unknown', 'yes', 'no')),
  affected_individuals integer not null default 0 check (affected_individuals >= 0),
  discovered_at timestamptz not null,
  reported_by_membership_id uuid not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  closed_at timestamptz,
  closed_by_membership_id uuid,
  close_note text,
  unique (tenant_id, id),
  foreign key (tenant_id, reported_by_membership_id) references tenant_memberships (tenant_id, id)
);

-- The four-factor risk assessment. Append-only: a reassessment is a new row and the latest one stands.
create table breach_assessments (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  incident_id uuid not null,
  nature_and_extent text not null check (length(nature_and_extent) between 3 and 2000),
  unauthorized_recipient text not null check (length(unauthorized_recipient) between 3 and 2000),
  acquired_or_viewed text not null check (length(acquired_or_viewed) between 3 and 2000),
  mitigation text not null check (length(mitigation) between 3 and 2000),
  risk text not null check (risk in ('low', 'not_low')),
  exception text not null default 'none' check (exception in ('none', 'unintentional_workforce_access',
    'inadvertent_internal_disclosure', 'unable_to_retain')),
  determination text not null check (determination in ('not_a_breach', 'breach')),
  assessed_by_membership_id uuid not null,
  assessed_at timestamptz not null default now(),
  foreign key (tenant_id, incident_id) references security_incidents (tenant_id, id),
  check (determination = 'breach' or risk = 'low' or exception <> 'none')
);

create table breach_notifications (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  incident_id uuid not null,
  audience text not null check (audience in ('individuals', 'hhs', 'media', 'covered_entity')),
  due_at timestamptz not null,
  sent_at timestamptz,
  method text,
  note text,
  recorded_by_membership_id uuid,
  created_at timestamptz not null default now(),
  unique (incident_id, audience),
  foreign key (tenant_id, incident_id) references security_incidents (tenant_id, id)
);

-- ------------------------------------------------------------------ M24 retention and rights
create table healthcare_retention_policies (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  resource_type text not null check (resource_type in ('call_content', 'call_recording')),
  retain_days integer not null check (retain_days between 1 and 36500),
  updated_by_membership_id uuid,
  updated_at timestamptz not null default now(),
  unique (tenant_id, resource_type)
);

create table legal_holds (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  scope text not null check (scope in ('all', 'call', 'phone')),
  call_id uuid,
  phone text,
  reason text not null check (length(reason) between 5 and 500),
  placed_by_membership_id uuid not null,
  placed_at timestamptz not null default now(),
  released_at timestamptz,
  released_by_membership_id uuid,
  release_reason text,
  check ((scope = 'call') = (call_id is not null)),
  check ((scope = 'phone') = (phone is not null))
);

create table retention_requests (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  kind text not null check (kind in ('access', 'amendment', 'deletion', 'restriction')),
  subject_phone text not null check (subject_phone ~ '^\+[1-9][0-9]{{6,14}}$'),
  subject_reference text not null default '' check (length(subject_reference) <= 100),
  details text not null default '' check (length(details) <= 2000),
  status text not null default 'received' check (status in ('received', 'approved', 'rejected', 'completed')),
  received_at timestamptz not null default now(),
  due_at timestamptz not null,
  created_by_membership_id uuid not null,
  decided_by_membership_id uuid,
  decided_at timestamptz,
  decision_reason text,
  completed_by_membership_id uuid,
  completed_at timestamptz,
  outcome jsonb,
  check (decided_by_membership_id is null or decided_by_membership_id <> created_by_membership_id),
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);

create table retention_runs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  started_by_membership_id uuid,
  ran_at timestamptz not null default now(),
  calls_purged integer not null default 0,
  skipped_on_hold integer not null default 0,
  details jsonb not null default '{{}}'
);

alter table calls add column content_purged_at timestamptz;

-- ------------------------------------------------------------------ M25 compliance evidence
-- tenant_id null: platform evidence (control-test runs). Customer BAAs are recorded only by a platform admin.
create table compliance_evidence (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references tenants(id) on delete cascade,
  kind text not null check (kind in ('customer_baa', 'control_test', 'risk_assessment', 'training',
    'policy_document', 'penetration_test', 'other')),
  title text not null check (length(title) between 3 and 200),
  status text not null default 'valid' check (status in ('valid', 'revoked')),
  valid_from date not null default current_date,
  valid_until date,
  reference text not null default '' check (length(reference) <= 300),
  details jsonb not null default '{{}}',
  recorded_by_user_id uuid,
  recorded_kind text not null check (recorded_kind in ('tenant', 'platform', 'system')),
  created_at timestamptz not null default now(),
  revoked_at timestamptz,
  revoked_reason text,
  check (valid_until is null or valid_until >= valid_from),
  check (kind <> 'customer_baa' or (tenant_id is not null and recorded_kind = 'platform')),
  check (kind <> 'control_test' or recorded_kind in ('platform', 'system'))
);
create index on compliance_evidence (tenant_id, kind, created_at desc);

create table compliance_risks (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  title text not null check (length(title) between 3 and 200),
  description text not null default '' check (length(description) <= 2000),
  likelihood integer not null check (likelihood between 1 and 5),
  impact integer not null check (impact between 1 and 5),
  mitigation text not null default '' check (length(mitigation) <= 2000),
  status text not null default 'open' check (status in ('open', 'mitigating', 'accepted', 'closed')),
  review_by date,
  created_by_membership_id uuid not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ------------------------------------------------------------------ call content purge (M24)
-- Deletes a call's transcript, empties its event and tool payloads and clears the other party's number. Only the
-- caller's own tenant, and never a call under an active legal hold (whole organisation, this call, or its number).
create or replace function purge_call_content(p_call uuid) returns boolean
language plpgsql security definer set search_path = public as $$
declare
  t uuid := app_tenant_id();
  c record;
begin
  if t is null then
    raise exception 'no tenant context';
  end if;
  select id, direction, from_number, to_number, content_purged_at into c
    from calls where id = p_call and tenant_id = t;
  if not found then
    return false;
  end if;
  if exists (
    select 1 from legal_holds h where h.tenant_id = t and h.released_at is null and (
      h.scope = 'all' or (h.scope = 'call' and h.call_id = p_call)
      or (h.scope = 'phone' and h.phone in (c.from_number, c.to_number)))
  ) then
    raise exception 'legal_hold' using errcode = 'P0001';
  end if;
  delete from transcript_segments where tenant_id = t and call_id = p_call;
  update call_events set data = '{{"purged": true}}'::jsonb where tenant_id = t and call_id = p_call;
  update tool_executions set input = '{{}}'::jsonb, result = null, error = null
    where tenant_id = t and call_id = p_call;
  update calls set content_purged_at = now(),
    from_number = case when direction = 'inbound' then null else from_number end,
    to_number = case when direction = 'outbound' then null else to_number end
    where tenant_id = t and id = p_call;
  return true;
end $$;
"""

FUNCTIONS = ("purge_call_content(uuid)",)

GRANTS = (
    r"""
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'xplovoice_app') then
    grant select, insert, update on healthcare_tenant_profiles, phi_data_classifications, security_incidents,
      breach_notifications, healthcare_retention_policies, legal_holds, retention_requests, compliance_risks
      to xplovoice_app;
    grant select, insert on vendor_compliance_records, phi_access_audit_logs, breach_assessments, retention_runs
      to xplovoice_app;  -- append-only
    grant select, insert, update (status, approved_by_membership_id, approved_at) on healthcare_policies
      to xplovoice_app;
    grant select, insert, update (status, revoked_at, revoked_reason) on compliance_evidence to xplovoice_app;
"""
    + "\n".join(f"    grant execute on function {f} to xplovoice_app;" for f in FUNCTIONS)
    + r"""
  end if;
  if exists (select 1 from pg_roles where rolname = 'xplovoice_definer') then
    grant select (id, tenant_id, direction, from_number, to_number, content_purged_at) on calls
      to xplovoice_definer;
    grant update (content_purged_at, from_number, to_number) on calls to xplovoice_definer;
    grant select on legal_holds to xplovoice_definer;
    grant select (tenant_id, call_id), delete on transcript_segments to xplovoice_definer;
    grant select (tenant_id, call_id), update (data) on call_events to xplovoice_definer;
    grant select (tenant_id, call_id), update (input, result, error) on tool_executions to xplovoice_definer;
"""
    + "\n".join(f"    alter function {f} owner to xplovoice_definer;" for f in FUNCTIONS)
    + "\n  end if;\nend $$;\n"
    + "\n".join(f"revoke execute on function {f} from public;" for f in FUNCTIONS)
)


def _rls() -> str:
    out: list[str] = [
        "alter table vendor_compliance_records enable row level security;",
        "alter table vendor_compliance_records force row level security;",
        "create policy vendor_read on vendor_compliance_records for select using (true);",
        "create policy vendor_write on vendor_compliance_records for insert with check (app_platform_admin());",
        "alter table compliance_evidence enable row level security;",
        "alter table compliance_evidence force row level security;",
        "create policy evidence_read on compliance_evidence for select "
        "using (tenant_id is null or tenant_id = app_tenant_id() or app_platform_admin());",
        # A tenant writes only its own evidence, and never a customer BAA or a control-test run.
        "create policy evidence_write on compliance_evidence for insert with check (app_platform_admin() or "
        "(tenant_id = app_tenant_id() and kind not in ('customer_baa', 'control_test') and recorded_kind = 'tenant'));",
        "create policy evidence_update on compliance_evidence for update "
        "using (app_platform_admin() or (tenant_id = app_tenant_id() and recorded_kind = 'tenant')) "
        "with check (app_platform_admin() or (tenant_id = app_tenant_id() and recorded_kind = 'tenant'));",
    ]
    for t in TENANT_TABLES:
        out += [
            f"alter table {t} enable row level security;",
            f"alter table {t} force row level security;",
            f"create policy {t}_tenant on {t} using (tenant_id = app_tenant_id()) "
            f"with check (tenant_id = app_tenant_id());",
        ]
    # The Super Admin healthcare console reads profiles and incidents across organisations and activates or
    # suspends a profile; it never reads PHI access logs, rights requests or call content of a tenant.
    out += [
        "create policy hc_profiles_admin on healthcare_tenant_profiles using (app_platform_admin()) "
        "with check (app_platform_admin());",
        "create policy hc_policies_admin_read on healthcare_policies for select using (app_platform_admin());",
        "create policy hc_incidents_admin_read on security_incidents for select using (app_platform_admin());",
        "create policy hc_assess_admin_read on breach_assessments for select using (app_platform_admin());",
        "create policy hc_retention_admin_read on healthcare_retention_policies for select "
        "using (app_platform_admin());",
    ]
    return "\n".join(out)


DOWNGRADE = (
    "\n".join(f"drop function if exists {f};" for f in FUNCTIONS)
    + "\ndrop table if exists compliance_evidence cascade;\n"
    + "drop table if exists vendor_compliance_records cascade;\n"
    + "\n".join(f"drop table if exists {t} cascade;" for t in reversed(TENANT_TABLES))  # noqa: S608 - fixed names
    + "\nalter table calls drop column if exists content_purged_at;\n"
    + "update tenant_memberships set role = 'viewer' where role = 'privacy_officer';\n"
    + "update invitations set role = 'viewer' where role = 'privacy_officer';\n"
    + "alter table tenant_memberships drop constraint tenant_memberships_role_check;\n"
    + f"alter table tenant_memberships add constraint tenant_memberships_role_check check (role in ({ROLES_OLD}));\n"
    + "alter table invitations drop constraint invitations_role_check;\n"
    + "alter table invitations add constraint invitations_role_check "
    "check (role in ('admin', 'agent_designer', 'operator', 'viewer'));\n"
)


def upgrade() -> None:
    op.execute(UPGRADE)
    op.execute(_rls())
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
