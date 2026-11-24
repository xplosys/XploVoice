// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use server";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { str } from "@/lib/actions";

async function setStatus(f: FormData, op: "suspend" | "reactivate") {
  let msg: string | null = null;
  try {
    await api(`/admin/v1/tenants/${encodeURIComponent(str(f, "id"))}/${op}`, { method: "POST", body: { reason: str(f, "reason") } });
  } catch (e) {
    if (!(e instanceof ApiError)) throw e;
    msg = e.message;
  }
  revalidatePath("/admin");
  if (msg) redirect(`/admin?error=${encodeURIComponent(msg)}`);
}

export async function suspendAction(f: FormData) { await setStatus(f, "suspend"); }
export async function reactivateAction(f: FormData) { await setStatus(f, "reactivate"); }
