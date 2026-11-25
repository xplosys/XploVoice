# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 3: common voice engine. Minimal agents with immutable versions (the full builder, M05, replaces the
editing surface in Phase 4), calls and their lifecycle (M08), append-only call events and transcript segments.

Every call pins one immutable agent version (MP section 9). Events are unique per (call, event key), so a
worker that retries or recovers after a crash can replay its writes safely (ADD-O10, CR-003).
Usage gains an `estimated` flag for the one case where a provider never reports usage: an LLM stream cancelled
by barge-in before its final usage chunk.

Revision ID: 0003_voice_engine
Revises: 0002_ai_providers
"""

from alembic import op

revision = "0003_voice_engine"
down_revision = "0002_ai_providers"
branch_labels = None
depends_on = None

UPGRADE = r"""
create table agents (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  name text not null check (length(name) between 1 and 120),
  status text not null default 'active' check (status in ('active', 'archived')),
  current_version_id uuid,
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);

create table agent_versions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  agent_id uuid not null,
  version integer not null check (version >= 1),
  config jsonb not null,
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  unique (tenant_id, agent_id, version),
  unique (tenant_id, id),
  foreign key (tenant_id, agent_id) references agents (tenant_id, id) on delete cascade,
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);
alter table agents add foreign key (tenant_id, current_version_id) references agent_versions (tenant_id, id)
  deferrable initially deferred;

create table calls (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  agent_id uuid not null,
  agent_version_id uuid not null,
  channel text not null check (channel in ('browser', 'sip')),
  direction text not null check (direction in ('test', 'inbound', 'outbound')),
  status text not null default 'created'
    check (status in ('created', 'dispatching', 'connecting', 'active', 'ending', 'completed', 'failed', 'abandoned')),
  end_reason text,
  room_name text not null unique,
  correlation_id text not null,
  language text,
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  connected_at timestamptz,
  ended_at timestamptz,
  duration_seconds numeric(10, 3),
  recoveries integer not null default 0,
  unique (tenant_id, id),
  foreign key (tenant_id, agent_id) references agents (tenant_id, id),
  foreign key (tenant_id, agent_version_id) references agent_versions (tenant_id, id),
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);
create index on calls (tenant_id, created_at desc);
create index on calls (tenant_id) where status not in ('completed', 'failed', 'abandoned');

create table call_events (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  call_id uuid not null,
  event_key text not null check (length(event_key) between 1 and 200),
  type text not null check (length(type) between 1 and 60),
  data jsonb not null default '{}',
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (tenant_id, call_id, event_key),
  foreign key (tenant_id, call_id) references calls (tenant_id, id) on delete cascade
);
create index on call_events (tenant_id, call_id, id);

create table transcript_segments (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  call_id uuid not null,
  seq integer not null check (seq >= 0),
  speaker text not null check (speaker in ('caller', 'agent')),
  text text not null,
  language text,
  start_ms integer,
  end_ms integer,
  interrupted boolean not null default false,
  created_at timestamptz not null default now(),
  unique (tenant_id, call_id, seq),
  foreign key (tenant_id, call_id) references calls (tenant_id, id) on delete cascade
);

alter table usage_events add column estimated boolean not null default false;

alter table agents enable row level security;
alter table agents force row level security;
create policy agent_tenant on agents using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());

alter table agent_versions enable row level security;
alter table agent_versions force row level security;
create policy agent_version_read on agent_versions for select using (tenant_id = app_tenant_id());
create policy agent_version_insert on agent_versions for insert with check (tenant_id = app_tenant_id());

alter table calls enable row level security;
alter table calls force row level security;
create policy call_tenant on calls using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());

alter table call_events enable row level security;
alter table call_events force row level security;
create policy call_event_read on call_events for select using (tenant_id = app_tenant_id());
create policy call_event_insert on call_events for insert with check (tenant_id = app_tenant_id());

alter table transcript_segments enable row level security;
alter table transcript_segments force row level security;
create policy transcript_read on transcript_segments for select using (tenant_id = app_tenant_id());
create policy transcript_insert on transcript_segments for insert with check (tenant_id = app_tenant_id());
"""

GRANTS = r"""
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'xplovoice_app') then
    grant select, insert, update on agents, calls to xplovoice_app;
    grant select, insert on agent_versions, call_events, transcript_segments to xplovoice_app;  -- append-only
  end if;
end $$;
"""

DOWNGRADE = r"""
alter table usage_events drop column if exists estimated;
drop table if exists transcript_segments;
drop table if exists call_events;
drop table if exists calls;
alter table if exists agents drop constraint if exists agents_tenant_id_current_version_id_fkey;
drop table if exists agent_versions;
drop table if exists agents;
"""


def upgrade() -> None:
    op.execute(UPGRADE)
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
