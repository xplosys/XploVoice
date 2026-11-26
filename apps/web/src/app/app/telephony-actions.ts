// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use server";
// Server actions for the Phase 6 screens: trunks, numbers and routes, queues, the destination policy, campaigns,
// the do-not-call list and consent. Every call goes through the API, which does all permission checks.
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api, type Campaign, type ImportResult } from "@/lib/api";
import { failure, opt, str, type ActionState } from "@/lib/actions";

const enc = encodeURIComponent;
const num = (f: FormData, k: string) => Number(str(f, k));
const NUMBERS = "/app/numbers";

async function call(path: string, method: string, body: unknown, revalidate: string[], ok = "Saved."): Promise<ActionState> {
  try {
    await api(path, { method, body });
  } catch (e) {
    return failure(e);
  }
  revalidate.forEach((p) => revalidatePath(p));
  return { ok };
}

// ------------------------------------------------------------------ trunks and numbers
export async function createTrunkAction(_: ActionState, f: FormData): Promise<ActionState> {
  const lines = str(f, "allowed_addresses").split(/[\s,]+/).filter(Boolean);
  return call("/v1/telephony/trunks", "POST", {
    name: str(f, "name"), provider_key: str(f, "provider_key"), direction: str(f, "direction"), address: opt(f, "address"),
    transport: str(f, "transport"), auth_username: opt(f, "auth_username"), auth_password: opt(f, "auth_password"),
    allowed_addresses: lines, billing_pulse_seconds: num(f, "billing_pulse_seconds") || 60,
  }, [NUMBERS], "Trunk added.");
}

export async function trunkStatusAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/telephony/trunks/${enc(str(f, "id"))}`, "PATCH", { status: str(f, "status") }, [NUMBERS]);
}

export async function syncTrunkAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/telephony/trunks/${enc(str(f, "id"))}/sync`, "POST", undefined, [NUMBERS], "Synced.");
}

export async function addNumberAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/phone-numbers", "POST", {
    number: str(f, "number"), trunk_id: str(f, "trunk_id"), label: str(f, "label"),
    inbound: f.get("inbound") === "on", outbound: f.get("outbound") === "on",
  }, [NUMBERS], "Number added.");
}

export async function releaseNumberAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/phone-numbers/${enc(str(f, "id"))}/release`, "POST", undefined, [NUMBERS], "Released.");
}

export async function routeAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  if (!str(f, "agent_id")) return call(`/v1/phone-numbers/${enc(id)}/route`, "DELETE", undefined, [NUMBERS], "Route removed.");
  return call(`/v1/phone-numbers/${enc(id)}/route`, "PUT", {
    agent_id: str(f, "agent_id"), queue_id: opt(f, "queue_id"), fallback_action: str(f, "fallback_action"),
    fallback_message: str(f, "fallback_message") || undefined, status: f.get("disabled") === "on" ? "disabled" : "active",
  }, [NUMBERS]);
}

export async function createQueueAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/queues", "POST", { name: str(f, "name"), max_waiting: num(f, "max_waiting") || 5,
    max_wait_seconds: num(f, "max_wait_seconds") || 60 }, [NUMBERS], "Queue added.");
}

export async function deleteQueueAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/queues/${enc(str(f, "id"))}`, "DELETE", undefined, [NUMBERS], "Queue removed.");
}

export async function policyAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/destination-policy", "PUT", {
    telephony_enabled: f.get("telephony_enabled") === "on", block_premium: f.get("block_premium") === "on",
    allowed_countries: str(f, "allowed_countries").split(/[\s,]+/).filter(Boolean),
    max_concurrent_outbound: num(f, "max_concurrent_outbound"), daily_outbound_minutes: num(f, "daily_outbound_minutes"),
  }, [NUMBERS]);
}

export async function killSwitchAction(_: ActionState, f: FormData): Promise<ActionState> {
  try {
    const p = await api<Record<string, unknown>>("/v1/destination-policy");
    await api("/v1/destination-policy", { method: "PUT", body: { ...p, telephony_enabled: str(f, "enable") === "true" } });
  } catch (e) {
    return failure(e);
  }
  revalidatePath(NUMBERS);
  return { ok: str(f, "enable") === "true" ? "Phone calls resumed." : "All phone calls are paused." };
}

export async function simulateInboundAction(_: ActionState, f: FormData): Promise<ActionState> {
  try {
    const r = await api<{ result: string; call_id: string | null; reason: string | null }>("/v1/telephony/simulate/inbound",
      { method: "POST", body: { to: str(f, "to"), caller: str(f, "caller") || undefined } });
    revalidatePath("/app/calls");
    return { ok: `Simulated call: ${r.result.replaceAll("_", " ")}${r.reason ? ` (${r.reason.replaceAll("_", " ")})` : ""}.`,
      data: r.call_id ? { call_id: r.call_id } : undefined };
  } catch (e) {
    return failure(e);
  }
}

export async function simulateEventAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  return call(`/v1/telephony/simulate/calls/${enc(id)}/event`, "POST", { status: str(f, "status") }, [`/app/calls/${id}`],
    "Carrier event sent.");
}

// ------------------------------------------------------------------ campaigns
function campaignBody(f: FormData) {
  return {
    name: str(f, "name"), purpose: str(f, "purpose"), agent_id: str(f, "agent_id"), from_number_id: str(f, "from_number_id"),
    timezone: str(f, "timezone"), window_start: str(f, "window_start"), window_end: str(f, "window_end"),
    days: f.getAll("days").map(String), max_attempts: num(f, "max_attempts"), retry_minutes: num(f, "retry_minutes"),
    max_concurrent: num(f, "max_concurrent"), calls_per_minute: num(f, "calls_per_minute"),
  };
}

export async function createCampaignAction(_: ActionState, f: FormData): Promise<ActionState> {
  let c: Campaign;
  try {
    c = await api<Campaign>("/v1/campaigns", { method: "POST", body: campaignBody(f) });
  } catch (e) {
    return failure(e);
  }
  revalidatePath("/app/campaigns");
  redirect(`/app/campaigns/${c.id}`);
}

export async function updateCampaignAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  return call(`/v1/campaigns/${enc(id)}`, "PUT", campaignBody(f), [`/app/campaigns/${id}`, "/app/campaigns"],
    "Saved. The campaign needs approval again.");
}

export async function campaignStepAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  const step = str(f, "step");
  const done: Record<string, string> = { approve: "Approved.", start: "Started. Calls begin within a few seconds.",
    pause: "Paused. Calls in progress finish normally.", cancel: "Cancelled." };
  return call(`/v1/campaigns/${enc(id)}/${enc(step)}`, "POST", undefined, [`/app/campaigns/${id}`, "/app/campaigns"],
    done[step] ?? "Done.");
}

/** One contact per line: phone, then optionally a name and an IANA time zone, separated by commas. */
export async function importContactsAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  const contacts = str(f, "contacts").split(/\r?\n/).map((l) => l.trim()).filter(Boolean).map((l) => {
    const [phone, name = "", timezone = ""] = l.split(",").map((x) => x.trim());
    return { phone, name, timezone: timezone || null };
  });
  if (contacts.length === 0) return { error: "Paste at least one phone number." };
  const basis = str(f, "consent_basis");
  try {
    const r = await api<ImportResult>(`/v1/campaigns/${enc(id)}/contacts`, { method: "POST", body: {
      contacts, consent_basis: basis || null, consent_evidence: str(f, "consent_evidence") } });
    revalidatePath(`/app/campaigns/${id}`);
    const bad = r.invalid.length ? ` ${r.invalid.length} skipped (rows ${r.invalid.map((x) => x.row).join(", ")}).` : "";
    const dnc = r.on_do_not_call_list ? ` ${r.on_do_not_call_list} on your do-not-call list will not be called.` : "";
    return { ok: `Added ${r.added}, ${r.duplicates} already in the list, consent recorded for ${r.consent_recorded}.${bad}${dnc}` };
  } catch (e) {
    return failure(e);
  }
}

export async function removeContactAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  return call(`/v1/campaigns/${enc(id)}/contacts/${enc(str(f, "contact"))}`, "DELETE", undefined, [`/app/campaigns/${id}`],
    "Removed.");
}

// ------------------------------------------------------------------ do not call and consent
const DNC = "/app/do-not-call";

export async function suppressAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/suppression", "POST", { phone: str(f, "phone"), reason: str(f, "reason"), note: str(f, "note") }, [DNC],
    "Added to the do-not-call list.");
}

export async function unsuppressAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/suppression/${enc(str(f, "id"))}/remove`, "POST", { reason: str(f, "reason") }, [DNC], "Taken off the list.");
}

export async function consentAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/consent", "POST", { phone: str(f, "phone"), purpose: str(f, "purpose"), status: str(f, "status"),
    basis: str(f, "basis"), evidence: str(f, "evidence") }, [DNC], "Consent recorded.");
}

export async function revokeConsentAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/consent/revoke", "POST", { phone: str(f, "phone"), purpose: str(f, "purpose"), reason: str(f, "reason") },
    [DNC], "Consent revoked.");
}
