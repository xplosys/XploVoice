// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use server";
// Super Admin healthcare actions. The API checks the platform-admin flag, the MFA session, the written reason, the
// activation gate and that the activating admin is not the person who asked for Healthcare Mode.
import { revalidatePath } from "next/cache";
import { api } from "@/lib/api";
import { failure, opt, str, type ActionState } from "@/lib/actions";

const PAGE = "/admin/healthcare";
const enc = encodeURIComponent;

async function call(path: string, body: unknown, ok: string): Promise<ActionState> {
  try {
    await api(path, { method: "POST", body });
  } catch (e) {
    return failure(e);
  }
  revalidatePath(PAGE);
  return { ok };
}

export async function activateAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/admin/v1/healthcare/tenants/${enc(str(f, "tenant_id"))}/activate`, { reason: str(f, "reason") }, "Healthcare Mode is on.");
}

export async function suspendHcAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/admin/v1/healthcare/tenants/${enc(str(f, "tenant_id"))}/suspend`, { reason: str(f, "reason") },
    "Suspended. New calls are refused; every protection stays on.");
}

export async function customerBaaAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/admin/v1/healthcare/tenants/${enc(str(f, "tenant_id"))}/baa`, {
    title: str(f, "title"), signed_on: str(f, "signed_on"), valid_until: opt(f, "valid_until"), reference: str(f, "reference"),
    reason: str(f, "reason"),
  }, "BAA recorded.");
}

export async function vendorAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/admin/v1/healthcare/vendors", {
    vendor_type: str(f, "vendor_type"), vendor_key: str(f, "vendor_key"), vendor_name: str(f, "vendor_name"),
    services: str(f, "services"), baa_status: str(f, "baa_status"), signed_on: opt(f, "signed_on"),
    expires_on: opt(f, "expires_on"), reference: str(f, "reference"), reason: str(f, "reason"),
  }, "Vendor record added.");
}

export async function controlTestsAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/admin/v1/healthcare/control-tests/run", { reason: str(f, "reason") }, "Control tests ran. The result is stored as evidence.");
}
