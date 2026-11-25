// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use server";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { opt, str } from "@/lib/actions";

async function run(fn: () => Promise<unknown>, ok: string) {
  let msg: string | null = null;
  try {
    await fn();
  } catch (e) {
    if (!(e instanceof ApiError)) throw e;
    msg = e.message;
  }
  revalidatePath("/admin/ai");
  redirect(msg ? `/admin/ai?error=${encodeURIComponent(msg)}` : `/admin/ai?ok=${encodeURIComponent(ok)}`);
}

const list = (v: string) => v.split(",").map((x) => x.trim()).filter(Boolean);

export async function updateProviderAction(f: FormData) {
  const body: Record<string, unknown> = { reason: str(f, "reason") };
  for (const k of ["status", "baa_status"]) if (opt(f, k)) body[k] = str(f, k);
  for (const k of ["managed_available", "phi_eligible"]) if (opt(f, k)) body[k] = str(f, k) === "true";
  if (opt(f, "rate_limit_rpm")) body.rate_limit_rpm = Number(str(f, "rate_limit_rpm"));
  if (opt(f, "base_url")) body.base_url = str(f, "base_url");
  await run(() => api(`/admin/v1/ai/providers/${encodeURIComponent(str(f, "id"))}`, { method: "PATCH", body }), "Provider updated.");
}

export async function addModelAction(f: FormData) {
  await run(() => api("/admin/v1/ai/models", { method: "POST", body: {
    provider_id: str(f, "provider_id"), kind: str(f, "kind"), model_key: str(f, "model_key"),
    display_name: str(f, "display_name"), languages: list(str(f, "languages")), streaming: f.get("streaming") === "on",
    function_calling: f.get("function_calling") === "on", reason: str(f, "reason"),
  } }), "Model added.");
}

export async function addPriceAction(f: FormData) {
  await run(() => api("/admin/v1/ai/rate-cards", { method: "POST", body: {
    model_id: str(f, "model_id"), unit: str(f, "unit"), unit_price: str(f, "unit_price"), currency: str(f, "currency"),
    source: str(f, "source"), reason: str(f, "reason"),
  } }), "Price added.");
}

export async function setDefaultsAction(f: FormData) {
  const kind = str(f, "kind");
  const model_ids = [0, 1, 2].map((i) => str(f, `model_${i}`)).filter(Boolean);
  await run(() => api(`/admin/v1/ai/routes/${encodeURIComponent(kind)}`, { method: "PUT", body: { model_ids, reason: str(f, "reason") } }),
    `Default ${kind.toUpperCase()} order saved.`);
}
