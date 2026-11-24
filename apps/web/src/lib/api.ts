// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import "server-only";
import { accessToken } from "./session";

export const API_URL = process.env.XV_API_INTERNAL_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
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
    throw new ApiError(res.status, d?.code ?? "error", d?.message ?? "Something went wrong");
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
