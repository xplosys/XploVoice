# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 7: commercial SaaS. Plans and their price lists, subscriptions, the tenant charge ledger, spending limits,
quotas and cost alerts, invoices, payments through a payment-provider adapter, FX and tax rates (M15), analytics
reads (M16) and the billing parts of the Super Admin console (M17).

Provider cost (provider_cost_ledger, Phase 2) and tenant charges (charge_ledger, here) stay separate (MP section
22). Charges are rated from measured usage at the plan price in force when the usage happened; there is no single
estimated per-minute price. Every charge carries a unique source key, so rating is idempotent.

Catalog tables (plans, prices, FX, tax) are platform data: every signed-in tenant may read them, only a
platform-admin context may write them, and prices, FX and tax rates are append-only (a change is a new row with a
later effective date). No commercial prices, FX rates or tax rates are seeded (awaiting configuration).

Tenant tables have FORCE RLS. A platform-admin context may also read them (commercial data for the Super Admin
billing console); it writes to a tenant only by switching to that tenant's context, so the tenant policy applies.
The charge ledger, invoice lines and payment events are append-only for the runtime role.

Revision ID: 0007_billing
Revises: 0006_telephony
"""

from alembic import op

revision = "0007_billing"
down_revision = "0006_telephony"
branch_labels = None
depends_on = None

METERS = (
    "'base_fee', 'phone_inbound_minute', 'phone_outbound_minute', 'llm_input_1k_tokens', 'llm_output_1k_tokens', "
    "'stt_minute', 'tts_1k_characters'"
)

CATALOG_TABLES = ("billing_plans", "plan_prices", "fx_rates", "tax_rates", "payment_providers")
TENANT_TABLES = (
    "subscriptions",
    "billing_settings",
    "charge_ledger",
    "billing_alerts",
    "invoices",
    "invoice_lines",
    "payments",
    "payment_events",
)

UPGRADE = rf"""
-- ------------------------------------------------------------------ catalog (platform data)
create table billing_plans (
  id uuid primary key default gen_random_uuid(),
  code text not null unique check (code ~ '^[a-z0-9][a-z0-9_-]{{1,39}}$'),
  name text not null check (length(name) between 1 and 80),
  description text not null default '',
  kind text not null check (kind in ('subscription', 'payg')),
  currency text not null check (currency in ('INR', 'USD')),
  status text not null default 'draft' check (status in ('draft', 'active', 'retired')),
  is_default boolean not null default false,
  trial_days integer not null default 0 check (trial_days between 0 and 90),
  -- Plan limits, enforced by the API: max_agents, max_concurrent_calls, max_phone_numbers (absent = no plan limit).
  limits jsonb not null default '{{}}',
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, currency),
  check (not is_default or status = 'active')
);
-- At most one default plan per currency: new organisations in that currency start on it.
create unique index billing_plans_one_default on billing_plans (currency) where is_default;

-- Append-only price list. unit_price is per meter unit (minute, 1,000 tokens, 1,000 characters, or the period
-- for base_fee). included_quantity is free each period; monthly_cap is a hard quota per period.
create table plan_prices (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references billing_plans(id),
  meter text not null check (meter in ({METERS})),
  unit_price numeric(24, 12) not null check (unit_price >= 0),
  included_quantity numeric(20, 6) not null default 0 check (included_quantity >= 0),
  monthly_cap numeric(20, 6) check (monthly_cap is null or monthly_cap > 0),
  effective_from timestamptz not null default now(),
  created_by uuid,
  created_at timestamptz not null default now(),
  unique (plan_id, meter, effective_from),
  check (meter <> 'base_fee' or (included_quantity = 0 and monthly_cap is null))
);

-- Rates entered by a platform admin with their source (no rates are invented or fetched).
create table fx_rates (
  id uuid primary key default gen_random_uuid(),
  base text not null check (base in ('INR', 'USD')),
  quote text not null check (quote in ('INR', 'USD')),
  rate numeric(24, 12) not null check (rate > 0),
  effective_from timestamptz not null default now(),
  source text not null check (length(source) between 3 and 200),
  created_by uuid,
  created_at timestamptz not null default now(),
  unique (base, quote, effective_from),
  check (base <> quote)
);

create table tax_rates (
  id uuid primary key default gen_random_uuid(),
  country_code text not null check (country_code in ('IN', 'US')),
  label text not null check (length(label) between 2 and 60),
  rate_percent numeric(6, 3) not null check (rate_percent >= 0 and rate_percent <= 50),
  effective_from timestamptz not null default now(),
  source text not null check (length(source) between 3 and 200),
  created_by uuid,
  created_at timestamptz not null default now(),
  unique (country_code, effective_from)
);

-- Payment-provider adapters. No payment gateway is contracted (Phase 0 section N): the test provider exists for
-- development and tests only and never moves money; a live gateway waits for a contract and keys.
create table payment_providers (
  key text primary key check (key ~ '^[a-z_]{{2,40}}$'),
  name text not null,
  status text not null check (status in ('available', 'development_only', 'awaiting_configuration')),
  description text not null
);
insert into payment_providers (key, name, status, description) values
  ('test', 'Test payment provider', 'development_only',
   'Simulates a card payment and its signed webhook. Development and test only: no money moves.'),
  ('gateway', 'Card and UPI payments', 'awaiting_configuration',
   'Online payments by card, UPI and net banking. Awaiting a payment gateway contract and keys.');

create sequence invoice_number_seq;

-- ------------------------------------------------------------------ tenant data
create table subscriptions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  plan_id uuid not null references billing_plans(id),
  status text not null check (status in ('trialing', 'active', 'past_due', 'cancelled')),
  started_at timestamptz not null default now(),
  trial_ends_at timestamptz,
  current_period_start timestamptz not null,
  current_period_end timestamptz not null,
  cancel_at_period_end boolean not null default false,
  pending_plan_id uuid references billing_plans(id),
  cancelled_at timestamptz,
  ended_at timestamptz,
  source text not null check (source in ('self_service', 'platform_admin', 'default_plan')),
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  check (current_period_end > current_period_start),
  check ((status = 'cancelled') = (ended_at is not null))
);
-- One open subscription per organisation.
create unique index subscriptions_one_open on subscriptions (tenant_id) where ended_at is null;

create table billing_settings (
  tenant_id uuid primary key references tenants(id) on delete cascade,
  spend_limit numeric(18, 2) check (spend_limit is null or spend_limit > 0),
  hard_limit boolean not null default false,
  alert_percents integer[] not null default '{{50, 80, 100}}'
    check (alert_percents <@ array[25, 50, 75, 80, 90, 100]::integer[]),
  billing_email text check (billing_email is null or billing_email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  legal_name text check (legal_name is null or length(legal_name) <= 160),
  address text check (address is null or length(address) <= 500),
  tax_id text check (tax_id is null or tax_id ~ '^[A-Za-z0-9-]{{5,20}}$'),
  updated_by_membership_id uuid,
  updated_at timestamptz not null default now()
);

-- Tenant charges (append-only). Credits and adjustments are new rows with a reason; nothing is rewritten.
create table charge_ledger (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  subscription_id uuid not null,
  period_start timestamptz not null,
  entry_type text not null check (entry_type in ('fee', 'usage', 'credit', 'adjustment')),
  meter text check (meter is null or meter in ({METERS})),
  source_key text not null check (length(source_key) between 4 and 200),
  quantity numeric(20, 6) not null default 0 check (quantity >= 0),
  included_applied numeric(20, 6) not null default 0 check (included_applied >= 0 and included_applied <= quantity),
  unit_price numeric(24, 12),
  plan_price_id uuid references plan_prices(id),
  amount numeric(24, 12) not null,
  currency text not null check (currency in ('INR', 'USD')),
  usage_event_id bigint,
  telephony_usage_id bigint,
  occurred_at timestamptz not null default now(),
  description text not null default '',
  reason text,
  created_by uuid,
  created_at timestamptz not null default now(),
  unique (tenant_id, source_key),
  foreign key (tenant_id, subscription_id) references subscriptions (tenant_id, id),
  check (entry_type not in ('credit') or amount <= 0),
  check (entry_type not in ('fee', 'usage') or amount >= 0),
  check (entry_type not in ('credit', 'adjustment') or reason is not null)
);
create index on charge_ledger (tenant_id, subscription_id, period_start);
create unique index on charge_ledger (usage_event_id) where usage_event_id is not null;
create unique index on charge_ledger (telephony_usage_id) where telephony_usage_id is not null;

create table billing_alerts (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  subscription_id uuid not null,
  period_start timestamptz not null,
  kind text not null check (kind in ('spend_threshold', 'quota_reached')),
  threshold integer not null default 0,
  meter text not null default '',
  amount numeric(24, 12),
  currency text,
  created_at timestamptz not null default now(),
  unique (tenant_id, subscription_id, period_start, kind, threshold, meter),
  foreign key (tenant_id, subscription_id) references subscriptions (tenant_id, id)
);

create table invoices (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  number text not null unique,
  subscription_id uuid not null,
  plan_name text not null,
  period_start timestamptz not null,
  period_end timestamptz not null,
  currency text not null check (currency in ('INR', 'USD')),
  subtotal numeric(18, 2) not null,
  tax_label text,
  tax_percent numeric(6, 3),
  tax_amount numeric(18, 2) not null default 0,
  total numeric(18, 2) not null,
  amount_paid numeric(18, 2) not null default 0 check (amount_paid >= 0),
  status text not null check (status in ('open', 'paid', 'void')),
  bill_to jsonb not null default '{{}}',
  issued_at timestamptz not null default now(),
  due_at timestamptz not null,
  paid_at timestamptz,
  voided_at timestamptz,
  void_reason text,
  unique (tenant_id, id),
  unique (tenant_id, subscription_id, period_start),
  foreign key (tenant_id, subscription_id) references subscriptions (tenant_id, id),
  check (total = subtotal + tax_amount),
  check ((status = 'void') = (voided_at is not null))
);
create index on invoices (tenant_id, issued_at desc);

create table invoice_lines (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  invoice_id uuid not null,
  position integer not null,
  entry_type text not null,
  meter text,
  description text not null,
  quantity numeric(20, 6) not null,
  included_quantity numeric(20, 6) not null default 0,
  unit_price numeric(24, 12),
  amount numeric(18, 2) not null,
  unique (invoice_id, position),
  foreign key (tenant_id, invoice_id) references invoices (tenant_id, id) on delete cascade
);

create table payments (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  invoice_id uuid not null,
  provider_key text not null references payment_providers(key),
  provider_ref text not null,
  amount numeric(18, 2) not null check (amount > 0),
  currency text not null check (currency in ('INR', 'USD')),
  status text not null default 'pending' check (status in ('pending', 'succeeded', 'failed')),
  failure_reason text,
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  unique (provider_key, provider_ref),
  unique (tenant_id, id),
  foreign key (tenant_id, invoice_id) references invoices (tenant_id, id)
);
-- One payment in flight per invoice.
create unique index payments_one_pending on payments (invoice_id) where status = 'pending';

-- Payment-provider webhook events, stored once (deduplicated by the provider's event id).
create table payment_events (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  provider_key text not null,
  event_id text not null,
  payment_id uuid not null,
  type text not null,
  applied boolean not null default false,
  received_at timestamptz not null default now(),
  unique (provider_key, event_id),
  foreign key (tenant_id, payment_id) references payments (tenant_id, id)
);

-- ------------------------------------------------------------------ cross-tenant lookups (ids only)
-- Payment webhooks arrive before the tenant is known; the billing job visits every organisation with an open
-- subscription.
create or replace function find_payment_by_ref(p_provider text, p_ref text)
returns table (tenant_id uuid, payment_id uuid) language sql stable security definer set search_path = public as $$
  select p.tenant_id, p.id from payments p where p.provider_key = p_provider and p.provider_ref = p_ref limit 1
$$;

create or replace function open_subscriptions()
returns table (tenant_id uuid, subscription_id uuid) language sql stable security definer
set search_path = public as $$
  select s.tenant_id, s.id from subscriptions s where s.ended_at is null
$$;
"""

FUNCTIONS = ("find_payment_by_ref(text, text)", "open_subscriptions()")

GRANTS = (
    r"""
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'xplovoice_app') then
    grant select, insert, update on billing_plans to xplovoice_app;
    grant select, insert on plan_prices, fx_rates, tax_rates to xplovoice_app;
    grant select on payment_providers to xplovoice_app;
    grant usage on sequence invoice_number_seq to xplovoice_app;
    grant select, insert, update on subscriptions, billing_settings to xplovoice_app;
    grant select, insert on charge_ledger, billing_alerts, invoice_lines to xplovoice_app;  -- append-only
    grant select, insert, update (status, amount_paid, paid_at, voided_at, void_reason) on invoices to xplovoice_app;
    grant select, insert, update (status, failure_reason, completed_at) on payments to xplovoice_app;
    grant select, insert, update (applied) on payment_events to xplovoice_app;
"""
    + "\n".join(f"    grant execute on function {f} to xplovoice_app;" for f in FUNCTIONS)
    + r"""
  end if;
  if exists (select 1 from pg_roles where rolname = 'xplovoice_definer') then
    grant select (id, tenant_id, provider_key, provider_ref) on payments to xplovoice_definer;
    grant select (id, tenant_id, ended_at) on subscriptions to xplovoice_definer;
"""
    + "\n".join(f"    alter function {f} owner to xplovoice_definer;" for f in FUNCTIONS)
    + "\n  end if;\nend $$;\n"
    + "\n".join(f"revoke execute on function {f} from public;" for f in FUNCTIONS)
)


def _rls() -> str:
    out: list[str] = []
    for t in CATALOG_TABLES:
        out += [
            f"alter table {t} enable row level security;",
            f"alter table {t} force row level security;",
            f"create policy catalog_read on {t} for select using (true);",
        ]
        if t != "payment_providers":
            out.append(f"create policy catalog_write on {t} for insert with check (app_platform_admin());")
    out.append(
        "create policy catalog_update on billing_plans for update using (app_platform_admin()) "
        "with check (app_platform_admin());"
    )
    for t in TENANT_TABLES:
        out += [
            f"alter table {t} enable row level security;",
            f"alter table {t} force row level security;",
            f"create policy {t}_tenant on {t} using (tenant_id = app_tenant_id()) "
            f"with check (tenant_id = app_tenant_id());",
            f"create policy {t}_admin_read on {t} for select using (app_platform_admin());",
        ]
    return "\n".join(out)


DOWNGRADE = (
    "\n".join(f"drop function if exists {f};" for f in FUNCTIONS)
    + "\n"
    + "\n".join(f"drop table if exists {t} cascade;" for t in reversed(TENANT_TABLES))  # noqa: S608 - fixed names
    + "\ndrop sequence if exists invoice_number_seq;\n"
    + "\n".join(f"drop table if exists {t} cascade;" for t in reversed(CATALOG_TABLES))
)


def upgrade() -> None:
    op.execute(UPGRADE)
    op.execute(_rls())
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
