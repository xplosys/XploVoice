// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use server";
// Server actions for the Phase 7 Billing page. Every call goes through the API, which does all permission checks.
import { revalidatePath } from "next/cache";
import { api, type Payment } from "@/lib/api";
import { failure, opt, str, type ActionState } from "@/lib/actions";

const BILLING = "/app/billing";

async function call(path: string, method: string, body: unknown, ok: string, extra: string[] = []): Promise<ActionState> {
  try {
    await api(path, { method, body });
  } catch (e) {
    return failure(e);
  }
  [BILLING, ...extra].forEach((p) => revalidatePath(p));
  return { ok };
}

export async function choosePlanAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/billing/subscription", "POST", { plan_id: str(f, "plan_id") }, "Plan saved.");
}

export async function cancelPlanAction(_: ActionState, _f: FormData): Promise<ActionState> {
  return call("/v1/billing/subscription/cancel", "POST", undefined, "Your plan ends when this period ends.");
}

export async function resumePlanAction(_: ActionState, _f: FormData): Promise<ActionState> {
  return call("/v1/billing/subscription/resume", "POST", undefined, "Your plan continues.");
}

export async function billingSettingsAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/billing/settings", "PUT", {
    spend_limit: opt(f, "spend_limit"), hard_limit: f.get("hard_limit") === "on",
    alert_percents: f.getAll("alert_percents").map(Number), billing_email: opt(f, "billing_email"),
    legal_name: opt(f, "legal_name"), address: opt(f, "address"), tax_id: opt(f, "tax_id"),
  }, "Saved.");
}

export async function payInvoiceAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  let p: Payment;
  try {
    p = await api<Payment>(`/v1/billing/invoices/${encodeURIComponent(id)}/pay`, {
      method: "POST", body: { provider: "test", outcome: str(f, "outcome") || "succeed" },
    });
  } catch (e) {
    return failure(e);
  }
  [BILLING, `${BILLING}/invoices/${id}`].forEach((x) => revalidatePath(x));
  return p.status === "succeeded" ? { ok: "Paid with the test provider. No money moved." }
    : { error: `The test payment failed: ${p.failure_reason ?? "declined"}.` };
}
