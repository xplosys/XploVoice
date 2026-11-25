# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 5: knowledge bases and retrieval (M12), native workflows (M11: booking calendars, holidays,
appointments, leads, CRM activity, follow-ups), support tickets and notifications (M14), integrations with a
transactional event outbox and signed webhooks (M13), and the controlled tool gateway (addendum G): tenant tool
policies and an execution record for every tool call. Every table is tenant-scoped with FORCE RLS.

Revision ID: 0005_knowledge_tools
Revises: 0004_agent_builder
"""

from alembic import op

revision = "0005_knowledge_tools"
down_revision = "0004_agent_builder"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "knowledge_bases",
    "kb_documents",
    "kb_chunks",
    "booking_calendars",
    "holidays",
    "appointments",
    "leads",
    "lead_activities",
    "follow_ups",
    "tickets",
    "ticket_comments",
    "notification_templates",
    "notifications",
    "tool_policies",
    "tool_executions",
    "integrations",
    "integration_events",
    "webhook_deliveries",
)

UPGRADE = r"""
alter table calls drop constraint if exists calls_channel_check;
alter table calls add constraint calls_channel_check check (channel in ('browser', 'sip', 'chat'));

-- ------------------------------------------------------------------ M12 knowledge bases
create table knowledge_bases (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  name text not null check (length(name) between 1 and 120),
  description text not null default '' check (length(description) <= 500),
  status text not null default 'active' check (status in ('active', 'archived')),
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);

-- Only extracted text is kept, never the uploaded file: less to protect, and nothing executable is stored.
create table kb_documents (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  kb_id uuid not null,
  title text not null check (length(title) between 1 and 200),
  source text not null check (source in ('upload', 'text')),
  filename text check (length(filename) <= 255),
  mime text,
  size_bytes integer not null check (size_bytes >= 0),
  sha256 text not null,
  status text not null default 'scanning' check (status in ('scanning', 'processing', 'ready', 'rejected', 'failed')),
  scan_engine text,
  scan_result text,
  error text check (length(error) <= 300),
  chunk_count integer not null default 0,
  char_count integer not null default 0,
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, kb_id, sha256),
  foreign key (tenant_id, kb_id) references knowledge_bases (tenant_id, id) on delete cascade,
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);
create index on kb_documents (tenant_id, kb_id, created_at desc);

create table kb_chunks (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  kb_id uuid not null,
  document_id uuid not null,
  seq integer not null,
  content text not null check (length(content) <= 4000),
  -- English stems plus the unstemmed words, so Hindi, Hinglish and names still match.
  tsv tsvector generated always as (to_tsvector('english', content) || to_tsvector('simple', content)) stored,
  unique (document_id, seq),
  foreign key (tenant_id, document_id) references kb_documents (tenant_id, id) on delete cascade
);
create index on kb_chunks using gin (tsv);
create index on kb_chunks (tenant_id, kb_id);

-- ------------------------------------------------------------------ M11 native workflows
create table booking_calendars (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  name text not null check (length(name) between 1 and 120),
  timezone text not null,
  slot_minutes integer not null default 30 check (slot_minutes between 5 and 240),
  weekly jsonb not null,
  min_notice_minutes integer not null default 60 check (min_notice_minutes between 0 and 10080),
  horizon_days integer not null default 30 check (horizon_days between 1 and 180),
  status text not null default 'active' check (status in ('active', 'archived')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id)
);

-- A holiday with no calendar closes the whole organization: every booking calendar and every agent's
-- business hours. One with a calendar closes only that calendar.
create table holidays (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  calendar_id uuid,
  day date not null,
  name text not null check (length(name) between 1 and 120),
  created_at timestamptz not null default now(),
  unique nulls not distinct (tenant_id, calendar_id, day),
  foreign key (tenant_id, calendar_id) references booking_calendars (tenant_id, id) on delete cascade
);

create table appointments (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  calendar_id uuid not null,
  reference text not null,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  status text not null default 'booked' check (status in ('booked', 'cancelled', 'completed', 'no_show')),
  customer_name text not null check (length(customer_name) between 1 and 120),
  customer_phone text,
  customer_email text,
  notes text not null default '' check (length(notes) <= 1000),
  source text not null check (source in ('call', 'chat', 'manual')),
  call_id uuid,
  cancelled_reason text check (length(cancelled_reason) <= 300),
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (ends_at > starts_at),
  unique (tenant_id, id),
  unique (tenant_id, reference),
  foreign key (tenant_id, calendar_id) references booking_calendars (tenant_id, id),
  foreign key (tenant_id, call_id) references calls (tenant_id, id),
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);
create unique index appointments_one_per_slot on appointments (tenant_id, calendar_id, starts_at) where status = 'booked';
create index on appointments (tenant_id, starts_at);

create table leads (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  name text not null check (length(name) between 1 and 120),
  phone text,
  email text,
  company text not null default '' check (length(company) <= 120),
  interest text not null default '' check (length(interest) <= 1000),
  budget text not null default '' check (length(budget) <= 120),
  timeline text not null default '' check (length(timeline) <= 120),
  score integer check (score between 0 and 100),
  status text not null default 'new' check (status in ('new', 'contacted', 'qualified', 'won', 'lost')),
  source text not null check (source in ('call', 'chat', 'manual')),
  call_id uuid,
  owner_membership_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  foreign key (tenant_id, call_id) references calls (tenant_id, id),
  foreign key (tenant_id, owner_membership_id) references tenant_memberships (tenant_id, id)
);
create index on leads (tenant_id, created_at desc);

-- CRM activity: append-only timeline of a lead.
create table lead_activities (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  lead_id uuid not null,
  kind text not null check (kind in ('created', 'note', 'call', 'status_change', 'follow_up')),
  body text not null default '' check (length(body) <= 2000),
  call_id uuid,
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, lead_id) references leads (tenant_id, id) on delete cascade,
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);
create index on lead_activities (tenant_id, lead_id, id desc);

-- ------------------------------------------------------------------ M14 support tickets
create table tickets (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  reference text not null,
  subject text not null check (length(subject) between 1 and 200),
  description text not null default '' check (length(description) <= 4000),
  priority text not null default 'normal' check (priority in ('low', 'normal', 'high', 'urgent')),
  status text not null default 'open' check (status in ('open', 'pending', 'resolved', 'closed')),
  requester_name text not null default '' check (length(requester_name) <= 120),
  requester_phone text,
  requester_email text,
  source text not null check (source in ('call', 'chat', 'manual', 'escalation')),
  call_id uuid,
  assignee_membership_id uuid,
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  resolved_at timestamptz,
  unique (tenant_id, id),
  unique (tenant_id, reference),
  foreign key (tenant_id, call_id) references calls (tenant_id, id),
  foreign key (tenant_id, assignee_membership_id) references tenant_memberships (tenant_id, id),
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);
create unique index tickets_one_escalation_per_call on tickets (tenant_id, call_id) where source = 'escalation';
create index on tickets (tenant_id, created_at desc);

create table ticket_comments (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  ticket_id uuid not null,
  body text not null check (length(body) between 1 and 4000),
  internal boolean not null default true,
  author_membership_id uuid,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, ticket_id) references tickets (tenant_id, id) on delete cascade,
  foreign key (tenant_id, author_membership_id) references tenant_memberships (tenant_id, id)
);

create table follow_ups (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  lead_id uuid,
  ticket_id uuid,
  appointment_id uuid,
  due_at timestamptz not null,
  channel text not null default 'call' check (channel in ('call', 'sms', 'email', 'task')),
  note text not null default '' check (length(note) <= 500),
  status text not null default 'open' check (status in ('open', 'done', 'cancelled')),
  source text not null check (source in ('call', 'chat', 'manual')),
  call_id uuid,
  assignee_membership_id uuid,
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  unique (tenant_id, id),
  foreign key (tenant_id, lead_id) references leads (tenant_id, id) on delete cascade,
  foreign key (tenant_id, ticket_id) references tickets (tenant_id, id) on delete cascade,
  foreign key (tenant_id, appointment_id) references appointments (tenant_id, id) on delete cascade,
  foreign key (tenant_id, call_id) references calls (tenant_id, id),
  foreign key (tenant_id, assignee_membership_id) references tenant_memberships (tenant_id, id),
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);
create index on follow_ups (tenant_id, status, due_at);

-- ------------------------------------------------------------------ M14 notifications
-- Agents may only send a template an admin approved; the text is fixed apart from named placeholders.
create table notification_templates (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  key text not null check (key ~ '^[a-z_]{2,40}$'),
  name text not null check (length(name) between 1 and 120),
  channel text not null check (channel in ('sms', 'email')),
  subject text check (length(subject) <= 200),
  body text not null check (length(body) between 1 and 1000),
  status text not null default 'draft' check (status in ('draft', 'approved', 'retired')),
  approved_by_membership_id uuid,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, key, channel),
  foreign key (tenant_id, approved_by_membership_id) references tenant_memberships (tenant_id, id)
);

create table notifications (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  template_id uuid not null,
  channel text not null check (channel in ('sms', 'email')),
  recipient text not null,
  body text not null,
  status text not null default 'queued' check (status in ('queued', 'held', 'sent', 'failed')),
  status_reason text,
  related_type text,
  related_id uuid,
  call_id uuid,
  idempotency_key text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, idempotency_key),
  foreign key (tenant_id, template_id) references notification_templates (tenant_id, id),
  foreign key (tenant_id, call_id) references calls (tenant_id, id)
);
create index on notifications (tenant_id, created_at desc);

-- ------------------------------------------------------------------ tool gateway (addendum G)
create table tool_policies (
  tenant_id uuid not null references tenants(id) on delete cascade,
  tool_key text not null,
  enabled boolean not null default true,
  require_approval boolean not null,
  updated_by_membership_id uuid,
  updated_at timestamptz not null default now(),
  primary key (tenant_id, tool_key),
  foreign key (tenant_id, updated_by_membership_id) references tenant_memberships (tenant_id, id)
);

create table tool_executions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  call_id uuid,
  agent_version_id uuid,
  tool_key text not null,
  idempotency_key text not null,
  status text not null check (status in ('succeeded', 'failed', 'rejected', 'pending_approval', 'approved', 'denied')),
  input jsonb not null default '{}',
  result jsonb,
  error text check (length(error) <= 300),
  attempts integer not null default 1,
  latency_ms integer,
  decided_by_membership_id uuid,
  decided_at timestamptz,
  decision_reason text check (length(decision_reason) <= 300),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, idempotency_key),
  foreign key (tenant_id, call_id) references calls (tenant_id, id),
  foreign key (tenant_id, agent_version_id) references agent_versions (tenant_id, id),
  foreign key (tenant_id, decided_by_membership_id) references tenant_memberships (tenant_id, id)
);
create index on tool_executions (tenant_id, created_at desc);
create index on tool_executions (tenant_id, call_id);
create index on tool_executions (tenant_id) where status = 'pending_approval';

-- ------------------------------------------------------------------ M13 integrations
create table integrations (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  provider text not null check (provider ~ '^[a-z0-9_]{2,40}$'),
  name text not null check (length(name) between 1 and 120),
  status text not null check (status in ('awaiting_configuration', 'active', 'disabled')),
  settings jsonb not null default '{}',
  events text[] not null default '{}',
  secret_ciphertext text,
  created_by_membership_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  foreign key (tenant_id, created_by_membership_id) references tenant_memberships (tenant_id, id)
);

-- Domain events written in the same transaction as the change (outbox), then delivered by the dispatcher.
create table integration_events (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  type text not null,
  payload jsonb not null,
  created_at timestamptz not null default now(),
  unique (tenant_id, id)
);

create table webhook_deliveries (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  event_id bigint not null,
  integration_id uuid not null,
  status text not null default 'pending' check (status in ('pending', 'retrying', 'succeeded', 'dead')),
  attempts integer not null default 0,
  next_attempt_at timestamptz not null default now(),
  last_status integer,
  last_error text check (length(last_error) <= 300),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (event_id, integration_id),
  foreign key (tenant_id, event_id) references integration_events (tenant_id, id) on delete cascade,
  foreign key (tenant_id, integration_id) references integrations (tenant_id, id) on delete cascade
);
create index on webhook_deliveries (next_attempt_at) where status in ('pending', 'retrying');

-- The dispatcher finds due deliveries across tenants through this one narrow function, then does all the
-- work under each delivery's own tenant context. It returns ids only.
create or replace function due_webhook_deliveries(p_limit integer)
returns table (id bigint, tenant_id uuid) language sql stable security definer set search_path = public as $$
  select d.id, d.tenant_id from webhook_deliveries d
  where d.status in ('pending', 'retrying') and d.next_attempt_at <= now()
  order by d.next_attempt_at limit least(p_limit, 100)
$$;
"""

GRANTS = r"""
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'xplovoice_app') then
    grant select, insert, update on knowledge_bases, kb_documents, booking_calendars, appointments, leads,
      follow_ups, tickets, notification_templates, notifications, tool_policies, tool_executions, integrations,
      webhook_deliveries to xplovoice_app;
    grant delete on kb_documents, kb_chunks, holidays to xplovoice_app;
    grant select, insert on kb_chunks, holidays, lead_activities, ticket_comments, integration_events
      to xplovoice_app;  -- append-only (chunks and holidays can be removed, never edited)
    grant execute on function due_webhook_deliveries(integer) to xplovoice_app;
  end if;
  if exists (select 1 from pg_roles where rolname = 'xplovoice_definer') then
    grant select (id, tenant_id, status, next_attempt_at) on webhook_deliveries to xplovoice_definer;
    alter function due_webhook_deliveries(integer) owner to xplovoice_definer;
  end if;
end $$;
revoke execute on function due_webhook_deliveries(integer) from public;
"""


def _rls() -> str:
    out = []
    for t in TENANT_TABLES:
        out.append(f"alter table {t} enable row level security;")
        out.append(f"alter table {t} force row level security;")
        out.append(
            f"create policy {t}_tenant on {t} using (tenant_id = app_tenant_id()) "
            f"with check (tenant_id = app_tenant_id());"
        )
    return "\n".join(out)


DOWNGRADE = (
    "drop function if exists due_webhook_deliveries(integer);\n"  # noqa: S608 - fixed table names from this file
    + "\n".join(f"drop table if exists {t} cascade;" for t in reversed(TENANT_TABLES))
    + """
alter table calls drop constraint if exists calls_channel_check;
alter table calls no force row level security;
delete from calls where channel = 'chat';
alter table calls force row level security;
alter table calls add constraint calls_channel_check check (channel in ('browser', 'sip'));
"""
)


def upgrade() -> None:
    op.execute(UPGRADE)
    op.execute(_rls())
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
