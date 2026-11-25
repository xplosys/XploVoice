// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use server";
// Server actions for the Phase 5 screens: knowledge bases, booking, leads, follow-ups, tickets, notifications,
// business tools and integrations. Every call goes through the API, which does all permission checks.
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api, type ChatReply, type ChatStart, type Integration, type KbHit, type KnowledgeBase, type Lead,
  type Ticket } from "@/lib/api";
import { failure, opt, str, type ActionState } from "@/lib/actions";

const enc = encodeURIComponent;

async function call(path: string, method: string, body: unknown, revalidate: string[], ok = "Saved."): Promise<ActionState> {
  try {
    await api(path, { method, body });
  } catch (e) {
    return failure(e);
  }
  revalidate.forEach((p) => revalidatePath(p));
  return { ok };
}

// ------------------------------------------------------------------ knowledge
export async function createKbAction(_: ActionState, f: FormData): Promise<ActionState> {
  let kb: KnowledgeBase;
  try {
    kb = await api<KnowledgeBase>("/v1/knowledge-bases", { method: "POST", body: { name: str(f, "name"), description: str(f, "description") } });
  } catch (e) {
    return failure(e);
  }
  revalidatePath("/app/knowledge");
  redirect(`/app/knowledge/${kb.id}`);
}

export async function kbStatusAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  return call(`/v1/knowledge-bases/${enc(id)}`, "PATCH", { status: str(f, "status") }, [`/app/knowledge/${id}`, "/app/knowledge"]);
}

export async function addTextAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  return call(`/v1/knowledge-bases/${enc(id)}/documents/text`, "POST", { title: str(f, "title"), text: str(f, "text") },
    [`/app/knowledge/${id}`], "Added.");
}

/** Called from the browser with the file already read as base64 (files up to 5 MB). */
export async function uploadDocAction(kbId: string, filename: string, contentBase64: string, title: string): Promise<ActionState> {
  return call(`/v1/knowledge-bases/${enc(kbId)}/documents`, "POST", { filename, content_base64: contentBase64, title },
    [`/app/knowledge/${kbId}`], "Uploaded.");
}

export async function deleteDocAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  return call(`/v1/knowledge-bases/${enc(id)}/documents/${enc(str(f, "doc"))}`, "DELETE", undefined, [`/app/knowledge/${id}`], "Removed.");
}

export async function searchKbAction(kbId: string, query: string): Promise<{ hits?: KbHit[]; error?: string }> {
  try {
    return { hits: await api<KbHit[]>(`/v1/knowledge-bases/${enc(kbId)}/search`, { method: "POST", body: { query } }) };
  } catch (e) {
    return { error: failure(e)?.error };
  }
}

// ------------------------------------------------------------------ booking
const ALL_WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

function weekly(f: FormData) {
  return Object.fromEntries(ALL_WEEK.map((d) => {
    const on = f.get(`${d}_on`) === "on";
    return [d, on ? [{ start: str(f, `${d}_start`) || "09:00", end: str(f, `${d}_end`) || "18:00" }] : []];
  }));
}

export async function saveCalendarAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  const body = {
    name: str(f, "name"), timezone: str(f, "timezone"), slot_minutes: Number(str(f, "slot_minutes") || 30),
    min_notice_minutes: Number(str(f, "min_notice_minutes") || 60), horizon_days: Number(str(f, "horizon_days") || 30),
    status: str(f, "status") || "active", weekly: weekly(f),
  };
  return call(id ? `/v1/booking-calendars/${enc(id)}` : "/v1/booking-calendars", id ? "PUT" : "POST", body, ["/app/appointments"]);
}

export async function addHolidayAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/holidays", "POST", { day: str(f, "day"), name: str(f, "name"), calendar_id: opt(f, "calendar_id") },
    ["/app/appointments"], "Holiday added.");
}

export async function removeHolidayAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/holidays/${enc(str(f, "id"))}`, "DELETE", undefined, ["/app/appointments"], "Removed.");
}

export async function bookAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/appointments", "POST", {
    calendar_id: str(f, "calendar_id"), start: str(f, "start"), customer_name: str(f, "customer_name"),
    customer_phone: opt(f, "customer_phone"), notes: str(f, "notes"),
  }, ["/app/appointments"], "Booked.");
}

export async function appointmentAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = enc(str(f, "id"));
  const op = str(f, "op");
  if (op === "cancel") return call(`/v1/appointments/${id}/cancel`, "POST", { reason: opt(f, "reason") }, ["/app/appointments"], "Cancelled.");
  if (op === "reschedule") return call(`/v1/appointments/${id}/reschedule`, "POST", { start: str(f, "start") }, ["/app/appointments"], "Moved.");
  if (op === "completed" || op === "no_show") return call(`/v1/appointments/${id}/status`, "POST", { status: op }, ["/app/appointments"]);
  return { error: "Unknown action" };
}

// ------------------------------------------------------------------ leads and follow-ups
export async function createLeadAction(_: ActionState, f: FormData): Promise<ActionState> {
  let lead: Lead;
  try {
    lead = await api<Lead>("/v1/leads", { method: "POST", body: {
      name: str(f, "name"), phone: opt(f, "phone"), email: opt(f, "email"), company: str(f, "company"),
      interest: str(f, "interest"), budget: str(f, "budget"), timeline: str(f, "timeline") } });
  } catch (e) {
    return failure(e);
  }
  revalidatePath("/app/leads");
  redirect(`/app/leads/${lead.id}`);
}

export async function leadStatusAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  return call(`/v1/leads/${enc(id)}`, "PATCH", { status: str(f, "status") }, [`/app/leads/${id}`, "/app/leads"]);
}

export async function leadNoteAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  return call(`/v1/leads/${enc(id)}/notes`, "POST", { body: str(f, "body"), kind: str(f, "kind") || "note" }, [`/app/leads/${id}`], "Added.");
}

export async function addFollowUpAction(_: ActionState, f: FormData): Promise<ActionState> {
  const local = str(f, "due_at"); // datetime-local, in the browser's time zone: offset sent alongside
  const offset = Number(str(f, "tz_offset") || 0);
  const due = new Date(new Date(`${local}:00Z`).getTime() + offset * 60000).toISOString();
  const lead = opt(f, "lead_id");
  return call("/v1/follow-ups", "POST", { due_at: due, channel: str(f, "channel") || "call", note: str(f, "note"), lead_id: lead },
    [lead ? `/app/leads/${lead}` : "/app/follow-ups", "/app/follow-ups"], "Follow-up added.");
}

export async function followUpAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/follow-ups/${enc(str(f, "id"))}`, "PATCH", { status: str(f, "status") }, ["/app/follow-ups", `/app/leads/${str(f, "lead_id")}`]);
}

// ------------------------------------------------------------------ tickets
export async function createTicketAction(_: ActionState, f: FormData): Promise<ActionState> {
  let t: Ticket;
  try {
    t = await api<Ticket>("/v1/tickets", { method: "POST", body: {
      subject: str(f, "subject"), description: str(f, "description"), priority: str(f, "priority") || "normal",
      requester_name: str(f, "requester_name"), requester_phone: opt(f, "requester_phone") } });
  } catch (e) {
    return failure(e);
  }
  revalidatePath("/app/tickets");
  redirect(`/app/tickets/${t.id}`);
}

export async function ticketAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  const body: Record<string, string> = {};
  if (str(f, "status")) body.status = str(f, "status");
  if (str(f, "priority")) body.priority = str(f, "priority");
  return call(`/v1/tickets/${enc(id)}`, "PATCH", body, [`/app/tickets/${id}`, "/app/tickets"]);
}

export async function ticketCommentAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  return call(`/v1/tickets/${enc(id)}/comments`, "POST", { body: str(f, "body") }, [`/app/tickets/${id}`], "Comment added.");
}

// ------------------------------------------------------------------ notifications
export async function createTemplateAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call("/v1/notification-templates", "POST", { key: str(f, "key"), name: str(f, "name"), channel: str(f, "channel"),
    subject: opt(f, "subject"), body: str(f, "body") }, ["/app/notifications"], "Saved as a draft. Approve it to let agents send it.");
}

export async function templateAction(_: ActionState, f: FormData): Promise<ActionState> {
  const body: Record<string, string> = {};
  for (const k of ["status", "body", "name"]) if (str(f, k)) body[k] = str(f, k);
  return call(`/v1/notification-templates/${enc(str(f, "id"))}`, "PATCH", body, ["/app/notifications"]);
}

// ------------------------------------------------------------------ business tools
export async function toolPolicyAction(_: ActionState, f: FormData): Promise<ActionState> {
  return call(`/v1/tools/${enc(str(f, "key"))}/policy`, "PUT",
    { enabled: f.get("enabled") === "on", require_approval: f.get("require_approval") === "on" }, ["/app/tools"]);
}

export async function decisionAction(_: ActionState, f: FormData): Promise<ActionState> {
  const d = str(f, "decision");
  return call(`/v1/tools/executions/${enc(str(f, "id"))}/decision`, "POST", { decision: d, reason: opt(f, "reason") },
    ["/app/tools"], d === "approve" ? "Approved and carried out." : "Denied.");
}

// ------------------------------------------------------------------ integrations
export async function createWebhookAction(_: ActionState, f: FormData): Promise<ActionState> {
  try {
    const w = await api<Integration>("/v1/integrations/webhooks", { method: "POST", body: {
      name: str(f, "name"), url: str(f, "url"), events: f.getAll("events").map(String) } });
    revalidatePath("/app/integrations");
    return { ok: "Webhook added. Copy the signing secret now: it isn't shown again.", data: { secret: w.secret ?? "" } };
  } catch (e) {
    return failure(e);
  }
}

export async function webhookAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = enc(str(f, "id"));
  if (str(f, "op") === "rotate") {
    try {
      const w = await api<Integration>(`/v1/integrations/${id}/rotate-secret`, { method: "POST" });
      return { ok: "New secret. Copy it now: it isn't shown again.", data: { secret: w.secret ?? "" } };
    } catch (e) {
      return failure(e);
    }
  }
  return call(`/v1/integrations/${id}`, "PATCH", { status: str(f, "op") }, ["/app/integrations"]);
}

// ------------------------------------------------------------------ text test chat
export async function startChatAction(agentId: string, versionId?: string): Promise<{ chat?: ChatStart; error?: string }> {
  try {
    return { chat: await api<ChatStart>(`/v1/agents/${enc(agentId)}/chat`, { method: "POST", body: { version_id: versionId || null } }) };
  } catch (e) {
    return { error: failure(e)?.error };
  }
}

export async function sendChatAction(callId: string, text: string): Promise<{ reply?: ChatReply; error?: string }> {
  try {
    return { reply: await api<ChatReply>(`/v1/calls/${enc(callId)}/chat`, { method: "POST", body: { text } }) };
  } catch (e) {
    return { error: failure(e)?.error };
  }
}
