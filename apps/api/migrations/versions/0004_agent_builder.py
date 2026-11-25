# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 4: agent builder (M05). The agent lifecycle (MP section 9: draft, testing, published, paused,
archived), the published version pointer, an append-only publication history (publish, rollback, pause,
resume, archive, restore), content hashes and change notes on the immutable versions, the ten platform
templates (MP section 10), and the exact provider and model versions each call used (ADD-F-07).

Revision ID: 0004_agent_builder
Revises: 0003_voice_engine
"""

import json

from alembic import op

revision = "0004_agent_builder"
down_revision = "0003_voice_engine"
branch_labels = None
depends_on = None

UPGRADE = r"""
alter table agents drop constraint if exists agents_status_check;
alter table agents add column description text not null default '' check (length(description) <= 500);
alter table agents add column template_key text;
alter table agents add column published_version_id uuid;
alter table agents add column published_at timestamptz;
alter table agents add foreign key (tenant_id, published_version_id) references agent_versions (tenant_id, id);

alter table agent_versions add column content_hash text;
alter table agent_versions add column note text check (length(note) <= 200);

-- Backfill as the schema owner: FORCE RLS would otherwise hide every row from this session.
alter table agents no force row level security;
alter table agent_versions no force row level security;
update agents a set status = case
    when a.status = 'archived' then 'archived'
    when exists (select 1 from calls c where c.agent_id = a.id) then 'testing'
    else 'draft' end;
update agent_versions set content_hash = encode(sha256(convert_to(config::text, 'UTF8')), 'hex');
alter table agents force row level security;
alter table agent_versions force row level security;

alter table agents alter column status set default 'draft';
alter table agents add constraint agents_status_check
  check (status in ('draft', 'testing', 'published', 'paused', 'archived'));
alter table agents add constraint agents_published_consistent
  check ((status in ('published', 'paused')) = (published_version_id is not null) or status = 'archived');
alter table agent_versions alter column content_hash set not null;
create index on agent_versions (tenant_id, agent_id, version desc);

create table agent_publications (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  agent_id uuid not null,
  version_id uuid,
  action text not null check (action in ('publish', 'rollback', 'pause', 'resume', 'archive', 'restore')),
  reason text check (length(reason) <= 300),
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, agent_id) references agents (tenant_id, id) on delete cascade,
  foreign key (tenant_id, version_id) references agent_versions (tenant_id, id),
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);
create index on agent_publications (tenant_id, agent_id, id desc);
alter table agent_publications enable row level security;
alter table agent_publications force row level security;
create policy agent_pub_read on agent_publications for select using (tenant_id = app_tenant_id());
create policy agent_pub_insert on agent_publications for insert with check (tenant_id = app_tenant_id());

-- Platform-owned starting configurations, readable by every tenant, changed only by migrations.
create table agent_templates (
  key text primary key check (key ~ '^[a-z_]{2,40}$'),
  name text not null,
  category text not null,
  description text not null,
  config jsonb not null,
  sort integer not null,
  status text not null default 'active' check (status in ('active', 'retired')),
  updated_at timestamptz not null default now()
);

alter table calls add column providers_used jsonb not null default '{}';
alter table calls add column options jsonb not null default '{}';
"""

GRANTS = r"""
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'xplovoice_app') then
    grant select, insert on agent_publications to xplovoice_app;  -- append-only history
    grant select on agent_templates to xplovoice_app;
  end if;
end $$;
"""

DOWNGRADE = r"""
alter table calls drop column if exists options;
alter table calls drop column if exists providers_used;
drop table if exists agent_templates;
drop table if exists agent_publications;
alter table agents drop constraint if exists agents_published_consistent;
alter table agents drop constraint if exists agents_status_check;
alter table agents no force row level security;
update agents set status = case when status = 'archived' then 'archived' else 'active' end;
alter table agents force row level security;
alter table agents alter column status set default 'active';
alter table agents add constraint agents_status_check check (status in ('active', 'archived'));
alter table agents drop constraint if exists agents_tenant_id_published_version_id_fkey;
alter table agents drop column if exists published_at;
alter table agents drop column if exists published_version_id;
alter table agents drop column if exists template_key;
alter table agents drop column if exists description;
drop index if exists agent_versions_tenant_id_agent_id_version_idx;
alter table agent_versions drop column if exists note;
alter table agent_versions drop column if exists content_hash;
"""


def _seed() -> None:
    from xplovoice_api.modules.m05_agents.schemas import AgentConfig
    from xplovoice_api.modules.m05_agents.templates import TEMPLATES

    conn = op.get_bind()
    for i, t in enumerate(TEMPLATES):
        cfg = AgentConfig.model_validate(t["config"]).model_dump(mode="json")
        conn.exec_driver_sql(
            "insert into agent_templates (key, name, category, description, config, sort) "
            "values (%(key)s, %(name)s, %(category)s, %(description)s, %(config)s::jsonb, %(sort)s)",
            {**{k: t[k] for k in ("key", "name", "category", "description")}, "config": json.dumps(cfg), "sort": i},
        )


def upgrade() -> None:
    op.execute(UPGRADE)
    _seed()
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
