// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use server";
// Super Admin billing actions. The API checks the platform-admin flag, the MFA session and the written reason.
import { revalidatePath } from "next/cache";
import { api } from "@/lib/api";
import { failure, opt, str, type ActionState } from "@/lib/actions";

const PAGE = "/admin/billing";
const enc = encodeURIComponent;
const METERS = ["phone_inbound_minute", "phone_outbound_minute", "llm_input_1k_tokens", "llm_output_1k_tokens", "stt_minute",
  "tts_1k_characters"];

async function call(path: string, body: unknown, ok: string): Promise<ActionState> {
  try {
    await api(path, { method: "POST", body });
  } catch (e) {
    return failure(e);
  }
  revalidatePath(PAGE);
  return { ok };
}

const num = (f: FormData, k: string) => (str(f, k) ? Number(str(f, k)) : undefined);

export async function createPlanAction(_: ActionState, f: FormData): Promise<ActionState> {
  const prices: Record<string, string | null>[] = [];
  if (str(f, "kind") === "subscription") prices.push({ meter: "base_fee", unit_price: str(f, "fee") || "0" });
  for (const m of METERS) {
    if (!str(f, `${m}.price`)) continue;
    prices.push({ meter: m, unit_price: str(f, `${m}.price`), included_quantity: str(f, `${m}.included`) || "0",
      monthly_cap: opt(f, `${m}.cap`) });
  }
  return call("/admin/v1/billing/plans", {
    code: str(f, "code"), name: str(f, "name"), description: str(f, "description"), kind: str(f, "kind"),
    currency: str(f, "currency"), trial_days: num(f, "trial_days") ?? 0, prices, reason: str(f, "reason"),
    limits: { max_agents: num(f, "max_agents"), max_concurrent_calls: num(f, "max_concurrent_calls"),
      max_phone_numbers: num(f, "max_phone_numbers") },
  }, "Plan created as a draft. Activate it to offer it.");
}

export async function addPriceAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/admin/v1/billing/plans/${enc(str(f, "id"))}/prices`, {
    meter: str(f, "meter"), unit_price: str(f, "unit_price"), included_quantity: str(f, "included_quantity") || "0",
    monthly_cap: opt(f, "monthly_cap"), reason: str(f, "reason"),
  }, "Price added. It applies to use from now on.");
}

export async function planStatusAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/admin/v1/billing/plans/${enc(str(f, "id"))}/status`, {
    status: str(f, "status"), is_default: f.get("is_default") === "on", reason: str(f, "reason"),
  }, "Saved.");
}

export async function assignPlanAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/admin/v1/billing/tenants/${enc(str(f, "tenant_id"))}/subscription`,
    { plan_id: str(f, "plan_id"), reason: str(f, "reason") }, "Plan assigned.");
}

export async function creditAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/admin/v1/billing/tenants/${enc(str(f, "tenant_id"))}/credits`,
    { amount: str(f, "amount"), reason: str(f, "reason") }, "Credit added to the current period.");
}

export async function closePeriodAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/admin/v1/billing/tenants/${enc(str(f, "tenant_id"))}/close-period`, { reason: str(f, "reason") },
    "Period closed and invoiced.");
}

export async function runBillingAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/admin/v1/billing/run", { reason: str(f, "reason") }, "Billing run finished.");
}

export async function voidInvoiceAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/admin/v1/billing/invoices/${enc(str(f, "invoice_id"))}/void`, { reason: str(f, "reason") }, "Invoice voided.");
}

export async function fxAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/admin/v1/billing/fx-rates", { base: str(f, "base"), quote: str(f, "quote"), rate: str(f, "rate"),
    source: str(f, "source"), reason: str(f, "reason") }, "Rate added.");
}

export async function taxAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/admin/v1/billing/tax-rates", { country_code: str(f, "country_code"), label: str(f, "label"),
    rate_percent: str(f, "rate_percent"), source: str(f, "source"), reason: str(f, "reason") }, "Tax rate added.");
}
