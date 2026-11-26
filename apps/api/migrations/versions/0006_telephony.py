# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 6: telephony (M04 carriers, SIP trunks, numbers, destination policies), inbound routing and queues (M06),
outbound campaigns with a policy engine (M07), consent records and the do-not-call list (M22-core), and the
15-state call lifecycle (addendum E, CR-003) with carrier references, verified and deduplicated carrier events and
a state-transition history.

Every tenant table has FORCE RLS. Lookups that must cross tenants before the tenant is known (which tenant owns a
dialled number, which call a carrier event is about, which campaign contacts are due) go through SECURITY DEFINER
functions owned by xplovoice_definer that return ids only.

Revision ID: 0006_telephony
Revises: 0005_knowledge_tools
"""

from alembic import op

revision = "0006_telephony"
down_revision = "0005_knowledge_tools"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "sip_trunks",
    "phone_numbers",
    "call_queues",
    "inbound_routes",
    "destination_policies",
    "call_provider_refs",
    "call_provider_events",
    "call_state_transitions",
    "telephony_usage",
    "consent_records",
    "suppression_entries",
    "campaigns",
    "campaign_contacts",
    "dial_attempts",
    "policy_decisions",
)

STATES = (
    "'initiated', 'queued', 'routing', 'ringing', 'answered', 'connected', 'in_progress', 'on_hold', "
    "'transferring', 'completed', 'failed', 'busy', 'no_answer', 'cancelled', 'disconnected'"
)

UPGRADE = rf"""
-- ------------------------------------------------------------------ M04 carrier catalog (platform data)
-- No carrier is contracted yet (Phase 0 section N), so no vendor is named: customers bring their own SIP trunk
-- through LiveKit SIP, XploVoice-managed numbers wait for a carrier contract, and a simulated carrier exists for
-- development and tests only.
create table telephony_providers (
  key text primary key check (key ~ '^[a-z_]{{2,40}}$'),
  name text not null,
  kind text not null check (kind in ('simulated', 'sip', 'managed')),
  status text not null check (status in ('available', 'development_only', 'awaiting_configuration')),
  description text not null,
  capabilities jsonb not null default '{{}}',
  note text
);
insert into telephony_providers (key, name, kind, status, description, capabilities, note) values
  ('simulated', 'Simulated carrier', 'simulated', 'development_only',
   'Plays carrier outcomes (answer, busy, no answer, failure) without dialling anyone. Development and tests only.',
   '{{"inbound": true, "outbound": true, "transfer": "refer", "dtmf": true, "billing_pulse_seconds": 60}}', null),
  ('sip', 'Your own SIP trunk', 'sip', 'available',
   'Connect a SIP trunk from any carrier you already use. Calls run through LiveKit SIP.',
   '{{}}', 'Capabilities depend on your carrier: set them on the trunk.'),
  ('managed', 'Numbers from XploVoice', 'managed', 'awaiting_configuration',
   'Buy numbers in India and the US directly from XploVoice.',
   '{{}}', 'Needs a carrier contract (awaiting configuration).');

-- ------------------------------------------------------------------ M04 trunks and numbers
create table sip_trunks (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  name text not null check (length(name) between 1 and 120),
  provider_key text not null references telephony_providers(key),
  direction text not null default 'both' check (direction in ('inbound', 'outbound', 'both')),
  address text check (address is null or length(address) <= 255),
  transport text not null default 'udp' check (transport in ('udp', 'tcp', 'tls')),
  auth_username text check (auth_username is null or length(auth_username) <= 120),
  auth_secret_ciphertext text,
  allowed_addresses text[] not null default '{{}}',
  capabilities jsonb not null default '{{}}',
  status text not null default 'active' check (status in ('active', 'disabled')),
  sync_status text not null default 'pending' check (sync_status in ('pending', 'synced', 'error', 'not_required')),
  sync_error text,
  livekit_inbound_trunk_id text,
  livekit_outbound_trunk_id text,
  livekit_dispatch_rule_id text,
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);

create table phone_numbers (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  e164 text not null check (e164 ~ '^\+[1-9][0-9]{{6,14}}$'),
  country_code text not null check (length(country_code) = 2),
  trunk_id uuid not null,
  label text not null default '' check (length(label) <= 120),
  inbound boolean not null default true,
  outbound boolean not null default true,
  status text not null default 'active' check (status in ('active', 'released')),
  created_at timestamptz not null default now(),
  unique (tenant_id, id),
  foreign key (tenant_id, trunk_id) references sip_trunks (tenant_id, id)
);
-- A number belongs to one organisation at a time, across all tenants (inbound routing depends on it).
create unique index phone_numbers_active_e164 on phone_numbers (e164) where status = 'active';

-- ------------------------------------------------------------------ M06 inbound routing and queues
create table call_queues (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  name text not null check (length(name) between 1 and 120),
  max_waiting integer not null default 5 check (max_waiting between 1 and 50),
  max_wait_seconds integer not null default 60 check (max_wait_seconds between 10 and 600),
  created_at timestamptz not null default now(),
  unique (tenant_id, id)
);

create table inbound_routes (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  phone_number_id uuid not null,
  agent_id uuid not null,
  queue_id uuid,
  fallback_action text not null default 'message' check (fallback_action in ('message', 'hangup')),
  fallback_message text not null default 'Sorry, all our lines are busy right now. Please call back a little later.'
    check (length(fallback_message) between 1 and 300),
  status text not null default 'active' check (status in ('active', 'disabled')),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (phone_number_id),
  foreign key (tenant_id, phone_number_id) references phone_numbers (tenant_id, id),
  foreign key (tenant_id, agent_id) references agents (tenant_id, id),
  foreign key (tenant_id, queue_id) references call_queues (tenant_id, id)
);

-- ------------------------------------------------------------------ M04 destination policy (toll-fraud controls)
create table destination_policies (
  tenant_id uuid primary key references tenants(id) on delete cascade,
  telephony_enabled boolean not null default true,  -- the organisation's emergency stop
  allowed_countries text[] not null,
  block_premium boolean not null default true,
  max_concurrent_outbound integer not null default 2 check (max_concurrent_outbound between 1 and 50),
  daily_outbound_minutes integer not null default 120 check (daily_outbound_minutes between 1 and 100000),
  updated_by_membership_id uuid,
  updated_at timestamptz not null default now(),
  foreign key (tenant_id, updated_by_membership_id) references tenant_memberships (tenant_id, id)
);

-- ------------------------------------------------------------------ M08 the 15-state lifecycle
alter table calls add column state text not null default 'initiated' check (state in ({STATES}));
alter table calls add column state_changed_at timestamptz;
alter table calls add column answered_at timestamptz;
alter table calls add column from_number text;
alter table calls add column to_number text;
alter table calls add column trunk_id uuid;
alter table calls add column phone_number_id uuid;
alter table calls add column campaign_id uuid;
alter table calls add column queue_id uuid;
alter table calls add column queued_at timestamptz;
alter table calls add constraint calls_trunk_fk foreign key (tenant_id, trunk_id) references sip_trunks (tenant_id, id);
alter table calls add constraint calls_number_fk
  foreign key (tenant_id, phone_number_id) references phone_numbers (tenant_id, id);
alter table calls add constraint calls_queue_fk foreign key (tenant_id, queue_id) references call_queues (tenant_id, id);
alter table calls drop constraint if exists calls_status_check;
alter table calls add constraint calls_status_check
  check (status in ('created', 'queued', 'dispatching', 'connecting', 'active', 'ending', 'completed', 'failed',
                    'abandoned'));
alter table calls no force row level security;
update calls set state = case status
  when 'created' then 'initiated' when 'dispatching' then 'queued' when 'connecting' then 'routing'
  when 'active' then 'in_progress' when 'ending' then 'in_progress' when 'completed' then 'completed'
  when 'failed' then 'failed' else 'cancelled' end,
  state_changed_at = coalesce(ended_at, connected_at, created_at);
alter table calls force row level security;
create index on calls (tenant_id, state);
create index on calls (tenant_id, campaign_id) where campaign_id is not null;

-- A carrier's id for a call or leg (LiveKit participant, SIP call id, simulated id). Unique per carrier, so an
-- event from the carrier finds exactly one call.
create table call_provider_refs (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  call_id uuid not null,
  provider_key text not null,
  kind text not null check (kind in ('call', 'participant', 'sip_call_id', 'room')),
  ref text not null check (length(ref) between 1 and 200),
  created_at timestamptz not null default now(),
  unique (provider_key, kind, ref),
  foreign key (tenant_id, call_id) references calls (tenant_id, id) on delete cascade
);

-- Every carrier event, verified, stored once (unique per carrier event id) before it may change a call.
create table call_provider_events (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  call_id uuid not null,
  provider_key text not null,
  event_id text not null check (length(event_id) between 1 and 200),
  type text not null,
  state text check (state is null or state in ({STATES})),
  occurred_at timestamptz not null,
  received_at timestamptz not null default now(),
  applied boolean not null,
  data jsonb not null default '{{}}',
  unique (provider_key, event_id),
  foreign key (tenant_id, call_id) references calls (tenant_id, id) on delete cascade
);

create table call_state_transitions (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  call_id uuid not null,
  from_state text not null,
  to_state text not null,
  source text not null check (source in ('engine', 'carrier', 'api', 'dialer', 'queue')),
  reason text,
  occurred_at timestamptz not null default now(),
  foreign key (tenant_id, call_id) references calls (tenant_id, id) on delete cascade
);
create index on call_state_transitions (tenant_id, call_id, id);

-- Carrier minutes in the carrier's billing pulse. No telephony prices exist yet (awaiting configuration), so
-- nothing is priced here; Phase 7 charging reads these rows.
create table telephony_usage (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  call_id uuid not null unique,
  provider_key text not null,
  trunk_id uuid,
  direction text not null check (direction in ('inbound', 'outbound')),
  country_code text,
  connected_seconds numeric(10, 3) not null check (connected_seconds >= 0),
  pulse_seconds integer not null check (pulse_seconds between 1 and 60),
  billed_seconds integer not null check (billed_seconds >= 0),
  created_at timestamptz not null default now(),
  foreign key (tenant_id, call_id) references calls (tenant_id, id) on delete cascade
);

-- ------------------------------------------------------------------ M22-core consent and do-not-call
create table consent_records (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  phone text not null check (phone ~ '^\+[1-9][0-9]{{6,14}}$'),
  purpose text not null check (purpose in ('outbound_calls', 'recording')),
  status text not null check (status in ('granted', 'declined', 'revoked')),
  basis text not null check (basis in ('express_written', 'express_verbal', 'existing_relationship', 'on_call',
                                       'other')),
  source text not null check (source in ('manual', 'import', 'call')),
  evidence text not null default '' check (length(evidence) <= 1000),
  call_id uuid,
  captured_by_membership_id uuid,
  captured_at timestamptz not null default now(),
  revoked_at timestamptz,
  revoked_reason text,
  unique (tenant_id, id),
  foreign key (tenant_id, call_id) references calls (tenant_id, id),
  foreign key (tenant_id, captured_by_membership_id) references tenant_memberships (tenant_id, id)
);
create index on consent_records (tenant_id, phone, purpose);

create table suppression_entries (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  phone text not null check (phone ~ '^\+[1-9][0-9]{{6,14}}$'),
  reason text not null check (reason in ('opt_out', 'do_not_call_registry', 'complaint', 'manual')),
  source text not null check (source in ('manual', 'import', 'call')),
  note text not null default '' check (length(note) <= 500),
  call_id uuid,
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  removed_at timestamptz,
  removed_by_membership_id uuid,
  removed_reason text,
  unique (tenant_id, id),
  foreign key (tenant_id, call_id) references calls (tenant_id, id),
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id),
  foreign key (tenant_id, removed_by_membership_id) references tenant_memberships (tenant_id, id)
);
create unique index suppression_active on suppression_entries (tenant_id, phone) where removed_at is null;

-- ------------------------------------------------------------------ M07 outbound campaigns
create table campaigns (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  name text not null check (length(name) between 1 and 120),
  purpose text not null default '' check (length(purpose) <= 500),
  agent_id uuid not null,
  from_number_id uuid not null,
  status text not null default 'draft'
    check (status in ('draft', 'approved', 'running', 'paused', 'completed', 'cancelled')),
  timezone text not null,
  window_start time not null default '10:00',
  window_end time not null default '18:00',
  days text[] not null default '{{mon,tue,wed,thu,fri}}',
  max_attempts integer not null default 2 check (max_attempts between 1 and 5),
  retry_minutes integer not null default 120 check (retry_minutes between 15 and 10080),
  max_concurrent integer not null default 1 check (max_concurrent between 1 and 10),
  calls_per_minute integer not null default 2 check (calls_per_minute between 1 and 30),
  approved_by_membership_id uuid,
  approved_at timestamptz,
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (window_start < window_end),
  unique (tenant_id, id),
  foreign key (tenant_id, agent_id) references agents (tenant_id, id),
  foreign key (tenant_id, from_number_id) references phone_numbers (tenant_id, id),
  foreign key (tenant_id, approved_by_membership_id) references tenant_memberships (tenant_id, id),
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);
alter table calls add constraint calls_campaign_fk
  foreign key (tenant_id, campaign_id) references campaigns (tenant_id, id);

create table campaign_contacts (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  campaign_id uuid not null,
  phone text not null check (phone ~ '^\+[1-9][0-9]{{6,14}}$'),
  name text not null default '' check (length(name) <= 120),
  timezone text,
  status text not null default 'pending'
    check (status in ('pending', 'calling', 'retry', 'completed', 'exhausted', 'blocked', 'opted_out', 'cancelled')),
  attempts integer not null default 0,
  next_attempt_at timestamptz not null default now(),
  last_outcome text,
  last_call_id uuid,
  block_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (campaign_id, phone),
  foreign key (tenant_id, campaign_id) references campaigns (tenant_id, id) on delete cascade
);
create index on campaign_contacts (tenant_id, campaign_id, status);
create index campaign_contacts_due on campaign_contacts (next_attempt_at) where status in ('pending', 'retry');

create table dial_attempts (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  campaign_id uuid not null,
  contact_id uuid not null,
  call_id uuid not null,
  attempt_no integer not null,
  outcome text check (outcome in ('answered', 'busy', 'no_answer', 'failed', 'cancelled')),
  sip_status integer,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  unique (contact_id, attempt_no),
  foreign key (tenant_id, campaign_id) references campaigns (tenant_id, id),
  foreign key (tenant_id, contact_id) references campaign_contacts (tenant_id, id),
  foreign key (tenant_id, call_id) references calls (tenant_id, id)
);

-- Every outbound policy decision with each check's result, kept for audit (append-only).
create table policy_decisions (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  campaign_id uuid,
  contact_id uuid,
  call_id uuid,
  phone text not null,
  purpose text not null check (purpose in ('outbound_call', 'transfer')),
  decision text not null check (decision in ('allow', 'defer', 'block')),
  reason text,
  checks jsonb not null,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, campaign_id) references campaigns (tenant_id, id),
  foreign key (tenant_id, contact_id) references campaign_contacts (tenant_id, id)
);
create index on policy_decisions (tenant_id, campaign_id, id desc);

-- ------------------------------------------------------------------ cross-tenant lookups (ids only)
create or replace function route_inbound_number(p_e164 text)
returns table (tenant_id uuid, phone_number_id uuid) language sql stable security definer
set search_path = public as $$
  select n.tenant_id, n.id from phone_numbers n where n.e164 = p_e164 and n.status = 'active' and n.inbound
  limit 1
$$;

create or replace function find_call_by_provider_ref(p_provider text, p_kind text, p_ref text)
returns table (tenant_id uuid, call_id uuid) language sql stable security definer set search_path = public as $$
  select r.tenant_id, r.call_id from call_provider_refs r
  where r.provider_key = p_provider and r.kind = p_kind and r.ref = p_ref limit 1
$$;

create or replace function find_call_by_room(p_room text)
returns table (tenant_id uuid, call_id uuid) language sql stable security definer set search_path = public as $$
  select c.tenant_id, c.id from calls c where c.room_name = p_room limit 1
$$;

create or replace function due_campaign_contacts(p_limit integer)
returns table (id uuid, tenant_id uuid) language sql stable security definer set search_path = public as $$
  select cc.id, cc.tenant_id from campaign_contacts cc
  join campaigns c on c.id = cc.campaign_id and c.status = 'running'
  where cc.status in ('pending', 'retry') and cc.next_attempt_at <= now()
  order by cc.next_attempt_at limit least(p_limit, 200)
$$;

create or replace function due_queued_calls(p_limit integer)
returns table (id uuid, tenant_id uuid) language sql stable security definer set search_path = public as $$
  select c.id, c.tenant_id from calls c where c.state = 'queued' and c.queue_id is not null
  order by c.queued_at limit least(p_limit, 200)
$$;

create or replace function active_running_campaigns()
returns table (id uuid, tenant_id uuid) language sql stable security definer set search_path = public as $$
  select c.id, c.tenant_id from campaigns c where c.status = 'running'
$$;
"""

FUNCTIONS = (
    "route_inbound_number(text)",
    "find_call_by_provider_ref(text, text, text)",
    "find_call_by_room(text)",
    "due_campaign_contacts(integer)",
    "due_queued_calls(integer)",
    "active_running_campaigns()",
)

GRANTS = (
    r"""
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'xplovoice_app') then
    grant select on telephony_providers to xplovoice_app;
    grant select, insert, update on sip_trunks, phone_numbers, call_queues, inbound_routes, destination_policies,
      consent_records, suppression_entries, campaigns, campaign_contacts, dial_attempts to xplovoice_app;
    grant delete on campaign_contacts, inbound_routes, call_queues to xplovoice_app;
    grant select, insert on call_provider_refs, call_state_transitions, telephony_usage, policy_decisions
      to xplovoice_app;  -- append-only histories
    grant select, insert, update (applied) on call_provider_events to xplovoice_app;
"""
    + "\n".join(f"    grant execute on function {f} to xplovoice_app;" for f in FUNCTIONS)
    + r"""
  end if;
  if exists (select 1 from pg_roles where rolname = 'xplovoice_definer') then
    grant select (id, tenant_id, e164, status, inbound) on phone_numbers to xplovoice_definer;
    grant select (tenant_id, call_id, provider_key, kind, ref) on call_provider_refs to xplovoice_definer;
    grant select (id, tenant_id, room_name, state, queue_id, queued_at) on calls to xplovoice_definer;
    grant select (id, tenant_id, campaign_id, status, next_attempt_at) on campaign_contacts to xplovoice_definer;
    grant select (id, tenant_id, status) on campaigns to xplovoice_definer;
"""
    + "\n".join(f"    alter function {f} owner to xplovoice_definer;" for f in FUNCTIONS)
    + "\n  end if;\nend $$;\n"
    + "\n".join(f"revoke execute on function {f} from public;" for f in FUNCTIONS)
)


def _rls() -> str:
    out = [
        "alter table telephony_providers enable row level security;",
        "alter table telephony_providers force row level security;",
        "create policy catalog_read on telephony_providers for select using (true);",
    ]
    for t in TENANT_TABLES:
        out.append(f"alter table {t} enable row level security;")
        out.append(f"alter table {t} force row level security;")
        out.append(
            f"create policy {t}_tenant on {t} using (tenant_id = app_tenant_id()) "
            f"with check (tenant_id = app_tenant_id());"
        )
    return "\n".join(out)


DOWNGRADE = (
    "\n".join(f"drop function if exists {f};" for f in FUNCTIONS)
    + "\nalter table calls drop constraint if exists calls_campaign_fk;\n"
    + "\n".join(f"drop table if exists {t} cascade;" for t in reversed(TENANT_TABLES))  # noqa: S608 - fixed names
    + """
drop table if exists telephony_providers;
alter table calls drop constraint if exists calls_trunk_fk;
alter table calls drop constraint if exists calls_number_fk;
alter table calls drop constraint if exists calls_queue_fk;
alter table calls no force row level security;
update calls set status = 'dispatching' where status = 'queued';
alter table calls force row level security;
alter table calls drop constraint if exists calls_status_check;
alter table calls add constraint calls_status_check
  check (status in ('created', 'dispatching', 'connecting', 'active', 'ending', 'completed', 'failed', 'abandoned'));
alter table calls drop column state, drop column state_changed_at, drop column answered_at, drop column from_number,
  drop column to_number, drop column trunk_id, drop column phone_number_id, drop column campaign_id,
  drop column queue_id, drop column queued_at;
"""
)


def upgrade() -> None:
    op.execute(UPGRADE)
    op.execute(_rls())
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
