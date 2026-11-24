# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 1 foundation: identity (M01), tenants (M02), platform audit (M17).

Every tenant-owned table has ENABLE + FORCE ROW LEVEL SECURITY and composite tenant-aware foreign keys
(LLD v1.3 section 4). The runtime role `xplovoice_app` gets only the grants it needs; audit rows are
append-only for it (INSERT + SELECT, no UPDATE/DELETE).

Revision ID: 0001_foundation
Revises:
"""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = ["tenants", "tenant_memberships", "invitations", "refresh_tokens", "audit_log"]

UPGRADE = r"""
create extension if not exists pgcrypto;
create extension if not exists citext;

-- ---------------------------------------------------------------- helpers
create or replace function app_tenant_id() returns uuid language sql stable as $$
  select nullif(current_setting('app.tenant_id', true), '')::uuid
$$;
create or replace function app_user_id() returns uuid language sql stable as $$
  select nullif(current_setting('app.user_id', true), '')::uuid
$$;
create or replace function app_platform_admin() returns boolean language sql stable as $$
  select coalesce(current_setting('app.platform_admin', true), '') = 'on'
$$;

-- ---------------------------------------------------------------- M01 identity (global, not tenant-owned)
create table users (
  id uuid primary key default gen_random_uuid(),
  email citext not null unique,
  password_hash text not null,
  display_name text not null check (length(display_name) between 1 and 120),
  email_verified_at timestamptz,
  mfa_secret_enc text,
  mfa_enabled_at timestamptz,
  is_platform_admin boolean not null default false,
  status text not null default 'active' check (status in ('active', 'disabled')),
  failed_login_count integer not null default 0,
  locked_until timestamptz,
  last_login_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- M02 tenants
create table tenants (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(name) between 1 and 160),
  slug text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
  country_code text not null check (country_code in ('IN', 'US')),
  timezone text not null,
  currency text not null check (currency in ('INR', 'USD')),
  default_language text not null,
  date_format text not null,
  business_phone text check (business_phone is null or business_phone ~ '^\+[1-9][0-9]{6,14}$'),
  industry text,
  website text,
  status text not null default 'active' check (status in ('active', 'suspended', 'closed')),
  suspended_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table tenant_memberships (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  user_id uuid not null references users(id) on delete cascade,
  role text not null check (role in ('owner', 'admin', 'agent_designer', 'operator', 'viewer')),
  status text not null default 'active' check (status in ('active', 'removed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, user_id),
  unique (tenant_id, id)
);
create index on tenant_memberships (user_id);

create table invitations (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  email citext not null,
  role text not null check (role in ('admin', 'agent_designer', 'operator', 'viewer')),
  token_hash text not null unique,
  invited_by_membership_id uuid not null,
  expires_at timestamptz not null,
  accepted_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, invited_by_membership_id) references tenant_memberships (tenant_id, id)
);
create index on invitations (tenant_id, email);

create table refresh_tokens (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  user_id uuid not null references users(id) on delete cascade,
  membership_id uuid not null,
  family_id uuid not null,
  token_hash text not null unique,
  mfa boolean not null default false,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  replaced_by uuid,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, membership_id) references tenant_memberships (tenant_id, id) on delete cascade
);
create index on refresh_tokens (family_id);

-- ---------------------------------------------------------------- M17 audit (append-only, hash-chained)
create table audit_log (
  id bigint generated always as identity primary key,
  tenant_id uuid references tenants(id) on delete set null,
  actor_user_id uuid,
  actor_kind text not null default 'user' check (actor_kind in ('user', 'service', 'platform_admin', 'anonymous')),
  action text not null,
  resource_type text,
  resource_id text,
  result text not null check (result in ('allowed', 'denied', 'success', 'failure')),
  reason text,
  ip_hash text,
  correlation_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  prev_hash text,
  event_hash text not null
);
create index on audit_log (tenant_id, created_at desc);

-- ---------------------------------------------------------------- row level security
alter table tenants enable row level security;
alter table tenants force row level security;
create policy tenant_self on tenants
  using (id = app_tenant_id() or app_platform_admin()
         or id in (select m.tenant_id from tenant_memberships m
                   where m.user_id = app_user_id() and m.status = 'active'))
  with check (id = app_tenant_id() or app_platform_admin());

alter table tenant_memberships enable row level security;
alter table tenant_memberships force row level security;
create policy membership_tenant on tenant_memberships
  using (tenant_id = app_tenant_id() or app_platform_admin())
  with check (tenant_id = app_tenant_id());
-- A signed-in user may list their own memberships across tenants (login, tenant switcher), read-only,
-- and only while no tenant context is set, so tenant-scoped queries never see other tenants' rows.
create policy membership_self_read on tenant_memberships for select
  using (user_id = app_user_id() and app_tenant_id() is null);

alter table invitations enable row level security;
alter table invitations force row level security;
create policy invitation_tenant on invitations
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());

alter table refresh_tokens enable row level security;
alter table refresh_tokens force row level security;
-- Tenant-scoped so an admin removing a member can revoke that member's sessions. Only hashes are stored.
create policy refresh_tenant on refresh_tokens
  using (tenant_id = app_tenant_id())
  with check (tenant_id = app_tenant_id());

alter table audit_log enable row level security;
alter table audit_log force row level security;
create policy audit_read on audit_log for select
  using (tenant_id = app_tenant_id() or app_platform_admin());
create policy audit_insert on audit_log for insert
  with check (tenant_id is null or tenant_id = app_tenant_id());

-- ---------------------------------------------------------------- narrow lookups that must run before
-- tenant context exists. SECURITY DEFINER, fixed search_path, return only the ids needed.
create or replace function lookup_refresh_token(p_hash text)
returns table (tenant_id uuid, user_id uuid) language sql stable security definer set search_path = public as $$
  select r.tenant_id, r.user_id from refresh_tokens r where r.token_hash = p_hash
$$;
create or replace function lookup_invitation(p_hash text)
returns table (tenant_id uuid) language sql stable security definer set search_path = public as $$
  select i.tenant_id from invitations i
  where i.token_hash = p_hash and i.accepted_at is null and i.revoked_at is null and i.expires_at > now()
$$;
-- Revokes every live session of the calling user across all tenants (password change). Callable only for
-- yourself: the predicate pins p_user to the authenticated user from the transaction context.
create or replace function revoke_my_sessions(p_user uuid)
returns integer language sql volatile security definer set search_path = public as $$
  with r as (
    update refresh_tokens set revoked_at = now()
    where user_id = p_user and p_user = app_user_id() and revoked_at is null
    returning 1
  ) select count(*)::integer from r
$$;
create or replace function slug_available(p_slug text)
returns boolean language sql stable security definer set search_path = public as $$
  select not exists (select 1 from tenants where slug = p_slug)
$$;
"""

GRANTS = r"""
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'xplovoice_app') then
    grant usage on schema public to xplovoice_app;
    grant select, insert, update on users, tenants, tenant_memberships, invitations, refresh_tokens
      to xplovoice_app;
    grant delete on refresh_tokens to xplovoice_app;
    grant select, insert on audit_log to xplovoice_app;   -- append-only
    grant execute on function app_tenant_id(), app_user_id(), app_platform_admin(),
      lookup_refresh_token(text), lookup_invitation(text), slug_available(text), revoke_my_sessions(uuid)
      to xplovoice_app;
  end if;
end $$;
revoke execute on function lookup_refresh_token(text), lookup_invitation(text), slug_available(text),
  revoke_my_sessions(uuid) from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'xplovoice_definer') then
    grant usage, create on schema public to xplovoice_definer;
    grant select (tenant_id, user_id, token_hash, revoked_at) on refresh_tokens to xplovoice_definer;
    grant update (revoked_at) on refresh_tokens to xplovoice_definer;
    grant select (tenant_id, token_hash, accepted_at, revoked_at, expires_at) on invitations to xplovoice_definer;
    grant select (slug) on tenants to xplovoice_definer;
    alter function lookup_refresh_token(text) owner to xplovoice_definer;
    alter function lookup_invitation(text) owner to xplovoice_definer;
    alter function slug_available(text) owner to xplovoice_definer;
    alter function revoke_my_sessions(uuid) owner to xplovoice_definer;
  end if;
end $$;
"""

DOWNGRADE = r"""
drop function if exists revoke_my_sessions(uuid);
drop function if exists slug_available(text);
drop function if exists lookup_invitation(text);
drop function if exists lookup_refresh_token(text);
drop table if exists audit_log;
drop table if exists refresh_tokens;
drop table if exists invitations;
drop policy if exists tenant_self on tenants;
drop table if exists tenant_memberships;
drop table if exists tenants;
drop table if exists users;
drop function if exists app_platform_admin();
drop function if exists app_user_id();
drop function if exists app_tenant_id();
"""


def upgrade() -> None:
    op.execute(UPGRADE)
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
