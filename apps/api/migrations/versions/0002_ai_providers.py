# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 2: AI provider registry and gateway (M03), usage metering and provider cost (M15, metering only).

Catalog tables (providers, models, rate cards, platform routes) are global: every signed-in tenant may read
them, only a platform-admin context may write them. Credentials, tenant routes, usage and cost are
tenant-owned with ENABLE + FORCE RLS. Usage and cost are append-only for the runtime role, and usage is
unique per (tenant, idempotency key, unit) so a replayed event is a no-op (MP section 22, ADD-O10).

Revision ID: 0002_ai_providers
Revises: 0001_foundation
"""

from alembic import op

revision = "0002_ai_providers"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

# Mock (dev/test only) models with clearly synthetic prices. Kept separate so tests can restore it.
MOCK_SEED = r"""
select set_config('app.platform_admin', 'on', true);
with p as (select id from ai_providers where key = 'mock')
insert into ai_models (provider_id, kind, model_key, display_name, languages, streaming, function_calling, voices)
select p.id, m.kind, m.key, m.name, array['en-IN','hi-IN','hi-Latn-IN','en-US'], true, m.fc, m.voices::jsonb
from p, (values
  ('llm', 'mock-chat', 'Mock chat model', true, '[]'),
  ('stt', 'mock-stt', 'Mock speech-to-text', false, '[]'),
  ('tts', 'mock-tts', 'Mock text-to-speech', false, '[{"id":"mock-voice","name":"Mock voice"}]')
) as m(kind, key, name, fc, voices);

insert into ai_rate_cards (model_id, unit, unit_price, currency, source)
select m.id, u.unit, u.price, 'USD', 'synthetic (mock provider, development only)'
from ai_models m join ai_providers p on p.id = m.provider_id,
  (values ('mock-chat', 'input_token', 0.000001), ('mock-chat', 'output_token', 0.000002),
          ('mock-stt', 'audio_second', 0.0001),
          ('mock-tts', 'character', 0.00001)) as u(model, unit, price)
where p.key = 'mock' and m.model_key = u.model;
"""

UPGRADE = r"""
-- ---------------------------------------------------------------- M03 catalog (global)
create table ai_providers (
  id uuid primary key default gen_random_uuid(),
  key text not null unique check (key ~ '^[a-z0-9_]{2,40}$'),
  name text not null,
  adapter text not null
    check (adapter in ('openai', 'anthropic', 'deepgram', 'elevenlabs', 'sarvam', 'piper', 'mock')),
  hosting text not null check (hosting in ('cloud', 'self_hosted', 'dev_only')),
  kinds text[] not null check (kinds <@ array['llm', 'stt', 'tts']::text[] and cardinality(kinds) > 0),
  base_url text check (base_url is null or base_url ~ '^https?://'),
  regions text[] not null default '{}',
  managed_available boolean not null default false,
  customer_keys_allowed boolean not null default true,
  phi_eligible boolean not null default false,
  baa_status text not null default 'none' check (baa_status in ('none', 'requested', 'signed')),
  rate_limit_rpm integer check (rate_limit_rpm is null or rate_limit_rpm > 0),
  status text not null default 'active' check (status in ('active', 'disabled')),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- A provider may handle PHI only with a signed BAA (HLD v1.3 healthcare routing).
  check (not phi_eligible or baa_status = 'signed')
);

create table ai_models (
  id uuid primary key default gen_random_uuid(),
  provider_id uuid not null references ai_providers(id),
  kind text not null check (kind in ('llm', 'stt', 'tts')),
  model_key text not null check (length(model_key) between 1 and 120),
  display_name text not null,
  languages text[] not null default '{}',
  streaming boolean not null default false,
  function_calling boolean not null default false,
  context_window integer,
  voices jsonb not null default '[]'::jsonb,
  regions text[] not null default '{}',
  status text not null default 'active' check (status in ('active', 'disabled')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (provider_id, kind, model_key)
);

create table ai_rate_cards (
  id uuid primary key default gen_random_uuid(),
  model_id uuid not null references ai_models(id),
  unit text not null check (unit in ('input_token', 'output_token', 'audio_second', 'character', 'request')),
  unit_price numeric(24, 12) not null check (unit_price >= 0),
  currency text not null check (currency in ('USD', 'INR')),
  effective_from timestamptz not null default now(),
  source text not null,
  created_by uuid,
  created_at timestamptz not null default now(),
  unique (model_id, unit, effective_from)
);

create table platform_ai_routes (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('llm', 'stt', 'tts')),
  priority integer not null check (priority between 1 and 10),
  model_id uuid not null references ai_models(id),
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  unique (kind, priority)
);

-- ---------------------------------------------------------------- M03 tenant-owned
create table ai_credentials (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  provider_id uuid not null references ai_providers(id),
  label text not null check (length(label) between 1 and 80),
  secret_enc text not null,
  secret_hint text not null,
  status text not null default 'active' check (status in ('active', 'revoked')),
  last_verified_at timestamptz,
  last_error text,
  created_by_membership_id uuid not null,
  created_at timestamptz not null default now(),
  revoked_at timestamptz,
  unique (tenant_id, id),
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);
create index on ai_credentials (tenant_id, provider_id) where status = 'active';

create table tenant_ai_routes (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  kind text not null check (kind in ('llm', 'stt', 'tts')),
  priority integer not null check (priority between 1 and 10),
  model_id uuid not null references ai_models(id),
  credential_id uuid,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  unique (tenant_id, kind, priority),
  foreign key (tenant_id, credential_id) references ai_credentials (tenant_id, id)
);

-- ---------------------------------------------------------------- M15 metering (append-only)
create table usage_events (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  idempotency_key text not null check (length(idempotency_key) between 8 and 200),
  occurred_at timestamptz not null default now(),
  kind text not null check (kind in ('llm', 'stt', 'tts')),
  provider_id uuid not null references ai_providers(id),
  model_id uuid not null references ai_models(id),
  account text not null check (account in ('managed', 'customer')),
  credential_id uuid,
  unit text not null check (unit in ('input_token', 'output_token', 'audio_second', 'character', 'request')),
  quantity numeric(20, 6) not null check (quantity >= 0),
  source_type text not null check (source_type in ('playground', 'call', 'test', 'system')),
  source_id text,
  correlation_id text,
  created_at timestamptz not null default now(),
  unique (tenant_id, idempotency_key, unit),
  unique (tenant_id, id)
);
create index on usage_events (tenant_id, occurred_at desc);

create table provider_cost_ledger (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  usage_event_id bigint not null unique,
  rate_card_id uuid references ai_rate_cards(id),
  unit_price numeric(24, 12),
  amount numeric(24, 12),
  currency text check (currency in ('USD', 'INR')),
  borne_by text not null check (borne_by in ('platform', 'customer')),
  priced boolean not null,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, usage_event_id) references usage_events (tenant_id, id),
  check (priced = (amount is not null))
);

-- ---------------------------------------------------------------- row level security
alter table ai_providers enable row level security;
alter table ai_providers force row level security;
create policy catalog_read on ai_providers for select using (true);
create policy catalog_write on ai_providers for insert with check (app_platform_admin());
create policy catalog_update on ai_providers for update using (app_platform_admin()) with check (app_platform_admin());

alter table ai_models enable row level security;
alter table ai_models force row level security;
create policy catalog_read on ai_models for select using (true);
create policy catalog_write on ai_models for insert with check (app_platform_admin());
create policy catalog_update on ai_models for update using (app_platform_admin()) with check (app_platform_admin());

alter table ai_rate_cards enable row level security;
alter table ai_rate_cards force row level security;
create policy catalog_read on ai_rate_cards for select using (true);
create policy catalog_write on ai_rate_cards for insert with check (app_platform_admin());

alter table platform_ai_routes enable row level security;
alter table platform_ai_routes force row level security;
create policy catalog_read on platform_ai_routes for select using (true);
create policy catalog_write on platform_ai_routes for insert with check (app_platform_admin());
create policy catalog_update on platform_ai_routes for update using (app_platform_admin()) with check (app_platform_admin());
create policy catalog_delete on platform_ai_routes for delete using (app_platform_admin());

alter table ai_credentials enable row level security;
alter table ai_credentials force row level security;
create policy credential_tenant on ai_credentials
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());

alter table tenant_ai_routes enable row level security;
alter table tenant_ai_routes force row level security;
create policy route_tenant on tenant_ai_routes
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());

alter table usage_events enable row level security;
alter table usage_events force row level security;
create policy usage_read on usage_events for select using (tenant_id = app_tenant_id() or app_platform_admin());
create policy usage_insert on usage_events for insert with check (tenant_id = app_tenant_id());

alter table provider_cost_ledger enable row level security;
alter table provider_cost_ledger force row level security;
create policy cost_read on provider_cost_ledger for select using (tenant_id = app_tenant_id() or app_platform_admin());
create policy cost_insert on provider_cost_ledger for insert with check (tenant_id = app_tenant_id());

-- ---------------------------------------------------------------- seed: provider adapters only.
-- No commercial models or prices are seeded: they change often and must be entered by a platform admin from
-- the provider's current price list. Only the dev/test mock provider gets models and synthetic prices.
-- Catalog writes need platform-admin context, even for the owner (FORCE RLS); scoped to this transaction.
select set_config('app.platform_admin', 'on', true);
insert into ai_providers (key, name, adapter, hosting, kinds, base_url, regions, customer_keys_allowed) values
  ('openai', 'OpenAI', 'openai', 'cloud', array['llm','stt','tts'], 'https://api.openai.com/v1', array['US'], true),
  ('anthropic', 'Anthropic', 'anthropic', 'cloud', array['llm'], 'https://api.anthropic.com', array['US'], true),
  ('deepgram', 'Deepgram', 'deepgram', 'cloud', array['stt'], 'https://api.deepgram.com', array['US'], true),
  ('elevenlabs', 'ElevenLabs', 'elevenlabs', 'cloud', array['tts'], 'https://api.elevenlabs.io', array['US'], true),
  ('sarvam', 'Sarvam AI', 'sarvam', 'cloud', array['stt','tts'], 'https://api.sarvam.ai', array['IN'], true),
  ('ollama', 'Ollama (self-hosted)', 'openai', 'self_hosted', array['llm'], null, '{}', false),
  ('faster_whisper', 'Faster-Whisper (self-hosted)', 'openai', 'self_hosted', array['stt'], null, '{}', false),
  ('piper', 'Piper (self-hosted)', 'piper', 'self_hosted', array['tts'], null, '{}', false),
  ('mock', 'Mock provider (development and tests only)', 'mock', 'dev_only', array['llm','stt','tts'], null, '{}', false);
"""

GRANTS = r"""
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'xplovoice_app') then
    grant select, insert, update on ai_providers, ai_models, ai_credentials, tenant_ai_routes to xplovoice_app;
    grant select, insert on ai_rate_cards to xplovoice_app;
    grant select, insert, update, delete on platform_ai_routes to xplovoice_app;
    grant delete on tenant_ai_routes to xplovoice_app;
    grant select, insert on usage_events, provider_cost_ledger to xplovoice_app;   -- append-only
  end if;
end $$;
"""

DOWNGRADE = r"""
drop table if exists provider_cost_ledger;
drop table if exists usage_events;
drop table if exists tenant_ai_routes;
drop table if exists ai_credentials;
drop table if exists platform_ai_routes;
drop table if exists ai_rate_cards;
drop table if exists ai_models;
drop table if exists ai_providers;
"""


def upgrade() -> None:
    op.execute(UPGRADE)
    op.execute(MOCK_SEED)
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
