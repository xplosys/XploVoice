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
