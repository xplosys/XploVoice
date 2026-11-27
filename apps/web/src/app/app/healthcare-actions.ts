// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use server";
// Server actions for the Phase 8 Healthcare pages. Every call goes through the API, which does all permission checks,
// the four-eyes rules and the PHI access log.
import { revalidatePath } from "next/cache";
import { api } from "@/lib/api";
import { failure, opt, str, type ActionState } from "@/lib/actions";

const HC = "/app/healthcare";
const enc = encodeURIComponent;

async function call(path: string, method: string, body: unknown, ok: string, pages: string[] = [HC]): Promise<ActionState> {
  try {
    await api(path, { method, body });
  } catch (e) {
    return failure(e);
  }
  pages.forEach((p) => revalidatePath(p));
  return { ok };
}

// ------------------------------------------------------------------ M19
export async function requestHealthcareAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/healthcare/request", "POST", {
    entity_type: str(f, "entity_type"), privacy_contact: str(f, "privacy_contact"),
    synthetic_data_only: f.get("synthetic_data_only") === "on",
  }, "Requested. Xplosys reviews the activation gate and turns Healthcare Mode on when every check passes.");
}

export async function withdrawHealthcareAction(_: ActionState, _f: FormData): Promise<ActionState> {
  return call("/v1/healthcare/withdraw", "POST", undefined, "Request withdrawn.");
}

export async function draftPolicyAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/healthcare/policies", "POST", {
    recording_mode: str(f, "recording_mode"), privacy_notice: str(f, "privacy_notice"),
    allow_outbound_campaigns: f.get("allow_outbound_campaigns") === "on", change_note: str(f, "change_note"),
  }, "Draft saved. Someone else with healthcare rights must approve it.");
}

export async function approvePolicyAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/healthcare/policies/${enc(str(f, "id"))}/approve`, "POST", undefined, "Approved. This version is now in force.");
}

export async function classifyAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/healthcare/classifications/${enc(str(f, "resource_type"))}`, "PUT",
    { classification: str(f, "classification") }, "Saved.");
}

// ------------------------------------------------------------------ M23
const INC = `${HC}/incidents`;

export async function reportIncidentAction(_: ActionState, f: FormData): Promise<ActionState> {
  const at = str(f, "discovered_at");
  return call("/v1/incidents", "POST", {
    title: str(f, "title"), summary: str(f, "summary"), category: str(f, "category"), severity: str(f, "severity"),
    phi_involved: str(f, "phi_involved") || "unknown", affected_individuals: Number(str(f, "affected_individuals") || 0),
    discovered_at: at ? new Date(at).toISOString() : new Date().toISOString(),
  }, "Reported. The privacy officer has been given the incident to assess.", [INC]);
}

export async function assessIncidentAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  return call(`/v1/incidents/${enc(id)}/assessment`, "POST", {
    nature_and_extent: str(f, "nature_and_extent"), unauthorized_recipient: str(f, "unauthorized_recipient"),
    acquired_or_viewed: str(f, "acquired_or_viewed"), mitigation: str(f, "mitigation"), risk: str(f, "risk"),
    exception: str(f, "exception") || "none",
  }, "Assessment recorded.", [INC, `${INC}/${id}`]);
}

export async function updateIncidentAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  return call(`/v1/incidents/${enc(id)}`, "PATCH", {
    severity: str(f, "severity"), phi_involved: str(f, "phi_involved"),
    affected_individuals: Number(str(f, "affected_individuals") || 0),
  }, "Saved.", [INC, `${INC}/${id}`]);
}

export async function noticeSentAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  return call(`/v1/incidents/${enc(id)}/notifications/${enc(str(f, "notification_id"))}/sent`, "POST",
    { method: str(f, "method"), note: str(f, "note") }, "Recorded as sent.", [INC, `${INC}/${id}`]);
}

export async function closeIncidentAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  return call(`/v1/incidents/${enc(id)}/close`, "POST", { note: str(f, "note") }, "Closed.", [INC, `${INC}/${id}`]);
}

// ------------------------------------------------------------------ M24
const RET = `${HC}/retention`;

export async function retentionPolicyAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/retention/policies/${enc(str(f, "resource_type"))}`, "PUT", { retain_days: Number(str(f, "retain_days")) },
    "Saved.", [RET, HC]);
}

export async function placeHoldAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/retention/holds", "POST", {
    scope: str(f, "scope"), call_id: opt(f, "call_id"), phone: opt(f, "phone"), reason: str(f, "reason"),
  }, "Hold placed. Nothing it covers will be removed.", [RET]);
}

export async function releaseHoldAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/retention/holds/${enc(str(f, "id"))}/release`, "POST", { reason: str(f, "reason") }, "Released.", [RET]);
}

export async function runRetentionAction(_: ActionState, _f: FormData): Promise<ActionState> {
  try {
    const r = await api<{ calls_purged: number; skipped_on_hold: number }>("/v1/retention/run", { method: "POST" });
    revalidatePath(RET);
    return { ok: `Removed the content of ${r.calls_purged} call(s); ${r.skipped_on_hold} kept under a legal hold.` };
  } catch (e) {
    return failure(e);
  }
}

export async function logRequestAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/retention/requests", "POST", {
    kind: str(f, "kind"), subject_phone: str(f, "subject_phone"), subject_reference: str(f, "subject_reference"),
    details: str(f, "details"),
  }, "Logged. Someone else must approve or reject it.", [RET]);
}

export async function decideRequestAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/retention/requests/${enc(str(f, "id"))}/decide`, "POST",
    { decision: str(f, "decision"), reason: str(f, "reason") }, "Decision recorded.", [RET]);
}

export async function completeRequestAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/retention/requests/${enc(str(f, "id"))}/complete`, "POST", { note: str(f, "note") }, "Completed.", [RET]);
}

// ------------------------------------------------------------------ M25
const COMP = `${HC}/compliance`;

export async function addEvidenceAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/compliance/evidence", "POST", {
    kind: str(f, "kind"), title: str(f, "title"), reference: str(f, "reference"),
    valid_until: opt(f, "valid_until"),
  }, "Recorded.", [COMP]);
}

export async function revokeEvidenceAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/compliance/evidence/${enc(str(f, "id"))}/revoke`, "POST", { reason: str(f, "reason") }, "Revoked.", [COMP]);
}

export async function addRiskAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/compliance/risks", "POST", {
    title: str(f, "title"), description: str(f, "description"), likelihood: Number(str(f, "likelihood")),
    impact: Number(str(f, "impact")), mitigation: str(f, "mitigation"), review_by: opt(f, "review_by"),
  }, "Added to the register.", [COMP]);
}

export async function riskStatusAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/compliance/risks/${enc(str(f, "id"))}`, "PATCH", { status: str(f, "status") }, "Saved.", [COMP]);
}
