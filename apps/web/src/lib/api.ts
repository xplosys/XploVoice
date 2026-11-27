// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import "server-only";
import { accessToken } from "./session";

export const API_URL = process.env.XV_API_INTERNAL_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: Record<string, unknown>) {
    super(message);
  }
}

type Init = { method?: string; body?: unknown; auth?: boolean; token?: string };

export async function api<T>(path: string, init: Init = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = init.token ?? (init.auth === false ? undefined : await accessToken());
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_URL}${path}`, {
    method: init.method ?? "GET",
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    cache: "no-store",
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data?.detail;
    if (Array.isArray(d)) {
      // Pydantic validation errors: surface the first human-readable message.
      const msg = String(d[0]?.msg ?? "Invalid input").replace(/^Value error, /, "");
      throw new ApiError(res.status, "validation_error", msg);
    }
    throw new ApiError(res.status, d?.code ?? "error", d?.message ?? "Something went wrong", d);
  }
  return data as T;
}

export type Me = {
  user_id: string; email: string; display_name: string; email_verified: boolean; mfa_enabled: boolean;
  is_platform_admin: boolean; tenant_id: string; tenant_name: string; role: string; permissions: string[];
};

export type Tenant = {
  id: string; name: string; slug: string; country_code: string; timezone: string; currency: string;
  default_language: string; date_format: string; business_phone: string | null; industry: string | null;
  website: string | null; status: string; created_at: string;
};

export type Country = {
  code: string; name: string; currency: string; default_timezone: string; timezones: string[];
  languages: { code: string; name: string }[]; date_format: string;
};

export type Member = {
  id: string; user_id: string; email: string; display_name: string; role: string; mfa_enabled: boolean;
  created_at: string;
};

export type Invitation = {
  id: string; email: string; role: string; expires_at: string; accepted_at: string | null; revoked_at: string | null;
};

export type AuditEvent = {
  id: number; created_at: string; actor_user_id: string | null; actor_kind: string; action: string;
  resource_type: string | null; resource_id: string | null; result: string; correlation_id: string | null;
};

export type MyTenant = { tenant_id: string; name: string; role: string; current: boolean };

export type Price = { unit: string; unit_price: string; currency: string; effective_from: string; source: string };
export type AiModel = {
  id: string; kind: string; model_key: string; display_name: string; languages: string[]; streaming: boolean;
  function_calling: boolean; context_window: number | null; voices: { id: string; name: string }[]; status: string;
  prices: Price[];
};
export type AiProvider = {
  id: string; key: string; name: string; hosting: string; kinds: string[]; regions: string[]; phi_eligible: boolean;
  customer_keys_allowed: boolean; managed_status: string; status: string; models: AiModel[];
};
export type AiCredential = {
  id: string; provider_key: string; provider_name: string; label: string; secret_hint: string; status: string;
  last_verified_at: string | null; last_error: string | null; created_at: string;
};
export type AiRoute = { priority: number; model_id: string; model: string; provider: string; credential_id: string | null;
  credential_label: string | null };
export type KindRoutes = { kind: "llm" | "stt" | "tts"; source: string; routes: AiRoute[] };
export type RouteCheck = { usable: { provider: string; model: string; account: string }[];
  skipped: { provider: string; model: string; reason: string }[] };
export type AiTest = { provider: string; model: string; account: string; text?: string | null; audio_base64?: string | null;
  mime?: string | null; units: Record<string, number>;
  attempts: { provider: string; model: string; outcome: string; error: string | null; latency_ms: number | null }[];
  skipped: { provider: string; model: string; reason: string }[] };
export type UsageRow = { day: string; kind: string; provider: string; model: string; account: string; unit: string;
  quantity: string; cost: string | null; currency: string | null; unpriced_events: number };
export type UsageEvent = { id: number; occurred_at: string; kind: string; provider: string; model: string; account: string;
  unit: string; quantity: string; source_type: string; cost: string | null; currency: string | null; borne_by: string | null };

export type Lang = "en-IN" | "hi-IN" | "hi-Latn-IN" | "en-US";
export type Win = { start: string; end: string };
export type Day = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
export type AgentConfig = {
  business_purpose: string; agent_type: string; system_prompt: string; personality: string; tone: string;
  greeting: string; language: Lang;
  ai: { llm_model_id: string | null; stt_model_id: string | null; tts_model_id: string | null; voice: string | null };
  knowledge_base_ids: string[]; tools: string[]; booking_calendar_id: string | null;
  business_hours: { enabled: boolean; timezone: string; weekly: Record<Day, Win[]>; after_hours: "answer" | "closed_message";
    closed_message: string };
  limits: { max_call_seconds: number; silence_timeout_seconds: number };
  interruption: { interruptible: boolean; barge_in_min_ms: number; endpoint_silence_ms: number };
  escalation: { enabled: boolean; phrases: string[]; max_unclear_turns: number; action: "transfer" | "take_message" | "end_call";
    message: string };
  transfer: { enabled: boolean; targets: { label: string; number: string }[]; announce: string; mode: "warm" | "cold" };
  recording: { policy: "off" | "record" | "ask_consent"; consent_message: string };
  fallback: { provider_failure_message: string; unclear_message: string; on_failure: "end_call" | "transfer" };
};
export type AgentStatus = "draft" | "testing" | "published" | "paused" | "archived";
export type Agent = { id: string; name: string; description: string; status: AgentStatus; template_key: string | null;
  version: number; version_id: string; config: AgentConfig; published_version: number | null;
  published_version_id: string | null; published_at: string | null; has_unpublished_changes: boolean; updated_at: string };
export type AgentVersion = { id: string; version: number; created_at: string; created_by: string | null; note: string | null;
  content_hash: string; is_published: boolean; was_published: boolean; test_calls: number };
export type AgentVersionDetail = AgentVersion & { config: AgentConfig };
export type ReadinessCheck = { key: string; level: "ok" | "warning" | "error"; message: string };
export type Readiness = { version: number; ready: boolean; tested: boolean; checks: ReadinessCheck[] };
export type Publication = { action: string; version: number | null; reason: string | null; actor: string | null;
  created_at: string };
export type AgentTemplate = { key: string; name: string; description: string; category: string; config: AgentConfig };
export type VoiceSession = { call_id: string; room: string; livekit_url: string; token: string; expires_in: number };
export type CallRow = { id: string; agent_id: string; agent_name: string; agent_version: number; channel: string;
  direction: string; status: string; end_reason: string | null; language: string | null; created_at: string;
  connected_at: string | null; ended_at: string | null; duration_seconds: string | null; recoveries: number;
  agent_version_id: string; state: string; answered_at: string | null; from_number: string | null;
  to_number: string | null; campaign_id: string | null;
  providers_used: Partial<Record<"llm" | "stt" | "tts", { provider: string; model: string; model_version: string; account: string }>>;
  phi_restricted?: boolean; content_purged?: boolean };
export type CallSegment = { seq: number; speaker: "caller" | "agent"; text: string; language: string | null;
  start_ms: number | null; end_ms: number | null; interrupted: boolean };
export type CallEvent = { type: string; data: Record<string, unknown>; occurred_at: string };
export type CallTransition = { from_state: string; to_state: string; source: string; reason: string | null; occurred_at: string };
export type CarrierEvent = { provider_key: string; type: string; state: string | null; applied: boolean; occurred_at: string;
  received_at: string };
export type CallDetail = CallRow & { transcript: CallSegment[]; events: CallEvent[]; transitions: CallTransition[];
  carrier_events: CarrierEvent[] };

// ------------------------------------------------------------------ Phase 5
export type KnowledgeBase = { id: string; name: string; description: string; status: "active" | "archived"; documents: number;
  ready_documents: number; chunks: number; created_at: string; updated_at: string; scanner: string };
export type KbDocument = { id: string; title: string; source: "upload" | "text"; filename: string | null; mime: string | null;
  size_bytes: number; status: "scanning" | "processing" | "ready" | "rejected" | "failed"; scan_engine: string | null;
  scan_result: string | null; error: string | null; chunk_count: number; char_count: number; created_at: string };
export type KbHit = { document_id: string; document: string; content: string; score: number };
export type Calendar = { id: string; name: string; timezone: string; slot_minutes: number; weekly: Record<Day, Win[]>;
  min_notice_minutes: number; horizon_days: number; status: "active" | "archived" };
export type Holiday = { id: string; day: string; name: string; calendar_id: string | null };
export type Appointment = { id: string; reference: string; calendar_id: string; calendar: string; timezone: string;
  starts_at: string; ends_at: string; local_start: string; status: "booked" | "cancelled" | "completed" | "no_show";
  customer_name: string; customer_phone: string | null; customer_email: string | null; notes: string; source: string;
  call_id: string | null; cancelled_reason: string | null; created_at: string };
export type Availability = { calendar: string; date: string; slots: { start: string; say: string }[]; note?: string;
  asked_date_note?: string };
export type Lead = { id: string; name: string; phone: string | null; email: string | null; company: string; interest: string;
  budget: string; timeline: string; score: number | null; status: "new" | "contacted" | "qualified" | "won" | "lost";
  source: string; call_id: string | null; created_at: string; updated_at: string };
export type FollowUp = { id: string; due_at: string; channel: string; note: string; status: "open" | "done" | "cancelled";
  source: string; lead_id: string | null; lead_name: string | null; ticket_id: string | null; appointment_id: string | null;
  call_id: string | null; completed_at: string | null };
export type LeadDetail = Lead & { activities: { kind: string; body: string; call_id: string | null; created_at: string }[];
  follow_ups: FollowUp[] };
export type Ticket = { id: string; reference: string; subject: string; description: string;
  priority: "low" | "normal" | "high" | "urgent"; status: "open" | "pending" | "resolved" | "closed"; requester_name: string;
  requester_phone: string | null; requester_email: string | null; source: string; call_id: string | null;
  assignee_membership_id: string | null; created_at: string; updated_at: string; resolved_at: string | null };
export type TicketDetail = Ticket & { comments: { body: string; internal: boolean; author_membership_id: string | null;
  created_at: string }[] };
export type NotificationTemplate = { id: string; key: string; name: string; channel: "sms" | "email"; subject: string | null;
  body: string; status: "draft" | "approved" | "retired"; approved_at: string | null; updated_at: string; placeholders: string[] };
export type NotificationRow = { id: string; channel: string; recipient: string; body: string; status: string;
  status_reason: string | null; related_type: string | null; related_id: string | null; call_id: string | null; created_at: string };
export type ToolInfo = { key: string; label: string; description: string; module: string; enabled: boolean;
  require_approval: boolean; sensitive_default: boolean; input_schema: Record<string, unknown> };
export type ToolExecution = { id: string; tool_key: string; label: string; status: string; call_id: string | null;
  input: Record<string, unknown>; result: Record<string, unknown> | null; error: string | null; latency_ms: number | null;
  attempts: number; decided_at: string | null; decision_reason: string | null; created_at: string };
export type IntegrationCatalog = { provider: string; name: string; category: string; description: string; status: string;
  note: string | null };
export type Integration = { id: string; provider: string; name: string; status: string; url: string | null; events: string[];
  created_at: string; secret: string | null };
export type Delivery = { id: number; event_type: string; status: string; attempts: number; last_status: number | null;
  last_error: string | null; next_attempt_at: string; created_at: string };
export type ChatStart = { call_id: string; agent_name: string; version: number; greeting: string | null };
export type ChatReply = { reply: string; tools: { name: string; status: string; execution_id: string }[];
  retrieval: { document: string; score: number }[]; ended: boolean; end_reason: string | null };

// ------------------------------------------------------------------ Phase 6 telephony
export type TelephonyProvider = { key: string; name: string; kind: string; status: string; description: string;
  capabilities: Record<string, unknown>; note: string | null };
export type Trunk = { id: string; name: string; provider_key: string; direction: "inbound" | "outbound" | "both";
  address: string | null; transport: string; auth_username: string | null; has_password: boolean; allowed_addresses: string[];
  billing_pulse_seconds: number; status: "active" | "disabled"; sync_status: string; sync_error: string | null; numbers: number;
  created_at: string; updated_at: string };
export type InboundRoute = { agent_id: string; agent_name: string; agent_status: string; queue_id: string | null;
  fallback_action: "message" | "hangup"; fallback_message: string; status: "active" | "disabled" };
export type PhoneNumber = { id: string; e164: string; country_code: string; trunk_id: string; trunk_name: string;
  provider_key: string; label: string; inbound: boolean; outbound: boolean; status: "active" | "released";
  route: InboundRoute | null; created_at: string };
export type CallQueue = { id: string; name: string; max_waiting: number; max_wait_seconds: number; waiting: number; created_at: string };
export type DestinationPolicy = { telephony_enabled: boolean; allowed_countries: string[]; block_premium: boolean;
  max_concurrent_outbound: number; daily_outbound_minutes: number; platform_enabled: boolean; live_outbound: number;
  outbound_minutes_today: number; updated_at: string };
export type Campaign = { id: string; name: string; purpose: string; agent_id: string; agent_name: string; from_number_id: string;
  from_number: string; timezone: string; window_start: string; window_end: string; days: string[]; max_attempts: number;
  retry_minutes: number; max_concurrent: number; calls_per_minute: number;
  status: "draft" | "approved" | "running" | "paused" | "completed" | "cancelled"; approved_by_membership_id: string | null;
  self_approved?: boolean;
  approved_at: string | null; created_by_membership_id: string | null; created_at: string; updated_at: string;
  counts: Record<string, number> };
export type CampaignContact = { id: string; phone: string; name: string; timezone: string | null; status: string; attempts: number;
  next_attempt_at: string; last_outcome: string | null; last_call_id: string | null; block_reason: string | null; updated_at: string };
export type PolicyCheck = { check: string; ok: boolean; detail: string };
export type PolicyDecision = { id: number; contact_id: string | null; call_id: string | null; phone: string;
  decision: "allow" | "defer" | "block"; reason: string | null; checks: PolicyCheck[]; created_at: string };
export type ImportResult = { added: number; duplicates: number; invalid: { row: number; phone: string; reason: string }[];
  consent_recorded: number; on_do_not_call_list: number };
export type ConsentRecord = { id: string; phone: string; purpose: string; status: string; basis: string; source: string;
  evidence: string; call_id: string | null; captured_at: string; revoked_at: string | null; revoked_reason: string | null };
export type SuppressionEntry = { id: string; phone: string; reason: string; source: string; note: string; call_id: string | null;
  created_at: string; removed_at: string | null; removed_reason: string | null };

// ------------------------------------------------------------------ Phase 7 billing and analytics
export type PlanPrice = { meter: string; label: string; unit: string; unit_price: string; included_quantity: string;
  monthly_cap: string | null; effective_from: string };
export type Plan = { id: string; code: string; name: string; description: string; kind: "subscription" | "payg";
  currency: string; status: string; is_default: boolean; trial_days: number; limits: Record<string, number>;
  prices: PlanPrice[] };
export type AdminPlan = Plan & { subscribers: number };
export type Subscription = { id: string; status: "trialing" | "active" | "past_due" | "cancelled"; plan: Plan;
  pending_plan: Plan | null; started_at: string; trial_ends_at: string | null; current_period_start: string;
  current_period_end: string; cancel_at_period_end: boolean; source: string };
export type MeterUsage = { meter: string; label: string; unit: string; quantity: string; included_used: string;
  included_quantity: string; monthly_cap: string | null; unit_price: string | null; amount: string };
export type BillingSettings = { spend_limit: string | null; hard_limit: boolean; alert_percents: number[];
  billing_email: string | null; legal_name: string | null; address: string | null; tax_id: string | null };
export type BillingOverview = { currency: string; subscription: Subscription | null; usage: MeterUsage[];
  period_total: string; settings: BillingSettings; alerts: { kind: string; threshold: number; meter: string | null;
  amount: string | null; created_at: string }[]; blocked: { code: string; message: string } | null;
  payment_providers: { key: string; name: string; status: string; description: string }[]; open_invoices: number };
export type LedgerEntry = { id: number; entry_type: string; meter: string | null; description: string; quantity: string;
  included_applied: string; unit_price: string | null; amount: string; currency: string; occurred_at: string;
  period_start: string; reason: string | null };
export type Invoice = { id: string; number: string; plan_name: string; period_start: string; period_end: string;
  currency: string; subtotal: string; tax_label: string | null; tax_percent: string | null; tax_amount: string;
  total: string; amount_paid: string; status: "open" | "paid" | "void"; issued_at: string; due_at: string;
  paid_at: string | null; voided_at: string | null; void_reason: string | null };
export type Payment = { id: string; provider_key: string; amount: string; currency: string; status: string;
  failure_reason: string | null; created_at: string; completed_at: string | null };
export type InvoiceDetail = Invoice & { bill_to: Record<string, string | null>; seller: Record<string, string>;
  lines: { position: number; entry_type: string; meter: string | null; description: string; quantity: string;
    included_quantity: string; unit_price: string | null; amount: string }[];
  payments: { id: string; provider_key: string; amount: string; currency: string; status: string;
    failure_reason: string | null; created_at: string; completed_at: string | null }[] };
export type Analytics = { days: number; timezone: string; currency: string;
  totals: { calls: number; completed: number; failed: number; in_progress: number; talk_minutes: string;
    average_seconds: string | null; transferred: number; escalated: number; contained_percent: string | null };
  by_day: { day: string; calls: number; completed: number; failed: number; talk_minutes: string; charges: string | null }[];
  by_agent: { agent_id: string; agent: string; calls: number; completed: number; average_seconds: string | null;
    transferred: number }[];
  by_channel: { key: string; count: number }[]; end_reasons: { key: string; count: number }[];
  outcomes: { appointments_booked: number; leads_created: number; tickets_created: number; tool_runs: number;
    tool_failures: number; opt_outs: number } };

// ------------------------------------------------------------------ Phase 8 healthcare (M19-M25)
export type GateCheck = { key: string; label: string; ok: boolean; detail: string };
export type HealthcarePolicy = { id: string; version: number; recording_mode: "off" | "consent_required"; privacy_notice: string;
  allow_outbound_campaigns: boolean; change_note: string; status: "draft" | "approved" | "superseded";
  created_by_membership_id: string; created_at: string; approved_by_membership_id: string | null; approved_at: string | null;
  written_by_you: boolean };
export type PhiClassification = { resource_type: string; classification: "phi" | "review" | "not_phi"; locked: boolean; note: string; updated_at: string };
export type Healthcare = { mode: "off" | "requested" | "active" | "suspended" | "withdrawn"; phi_protections: boolean;
  platform_enabled: boolean; environment: string;
  profile: { status: string; jurisdiction: string; entity_type: string; privacy_contact: string; synthetic_data_only: boolean;
    requested_at: string; activated_at: string | null; suspended_at: string | null; suspended_reason: string | null } | null;
  policy_version_in_force: number | null; gate: GateCheck[]; gate_passed: boolean; policies: HealthcarePolicy[];
  classifications: PhiClassification[] };
export type VendorEligibility = { vendor_type: string; vendor_key: string; name: string; kinds: string[]; eligible: boolean;
  reason: string; baa_expires_on: string | null };
export type PhiAccessRow = { id: number; actor_user_id: string | null; actor_kind: string; action: string; resource_type: string;
  resource_id: string | null; purpose: string; result: "allowed" | "denied"; reason: string | null; correlation_id: string | null;
  occurred_at: string };
export type Incident = { id: string; title: string; summary: string; category: string; severity: string; status: string;
  phi_involved: string; affected_individuals: number; discovered_at: string; created_at: string; closed_at: string | null;
  close_note: string | null; determination: string | null; next_due_at: string | null };
export type BreachAssessment = { id: string; nature_and_extent: string; unauthorized_recipient: string; acquired_or_viewed: string;
  mitigation: string; risk: string; exception: string; determination: string; assessed_at: string };
export type BreachNotice = { id: string; audience: string; due_at: string; sent_at: string | null; method: string | null; note: string | null };
export type IncidentDetail = Incident & { assessments: BreachAssessment[]; notifications: BreachNotice[] };
export type RetentionOverview = {
  policies: { resource_type: string; retain_days: number; updated_at: string }[];
  holds: { id: string; scope: string; call_id: string | null; phone: string | null; reason: string; placed_at: string;
    released_at: string | null; release_reason: string | null }[];
  requests: { id: string; kind: string; subject_phone: string; subject_reference: string; details: string; status: string;
    received_at: string; due_at: string; created_by_membership_id: string; decided_at: string | null; decision_reason: string | null;
    completed_at: string | null; outcome: Record<string, unknown> | null; logged_by_you: boolean }[];
  runs: { id: string; ran_at: string; calls_purged: number; skipped_on_hold: number }[] };
export type Evidence = { id: string; tenant_id: string | null; kind: string; title: string; status: string; valid_from: string;
  valid_until: string | null; reference: string; details: Record<string, unknown>; recorded_kind: string; created_at: string;
  revoked_at: string | null; revoked_reason: string | null };
export type Risk = { id: string; title: string; description: string; likelihood: number; impact: number; score: number;
  mitigation: string; status: string; review_by: string | null; created_at: string; updated_at: string };
export type ComplianceReport = { organisation: string; generated_at: string; mode: string; gate: GateCheck[]; evidence: Evidence[];
  open_risks: Risk[]; open_incidents: number; retention: Record<string, number>; phi_accesses_30_days: number;
  phi_denials_30_days: number; rights_requests_open: number; rights_requests_overdue: number; statement: string };
