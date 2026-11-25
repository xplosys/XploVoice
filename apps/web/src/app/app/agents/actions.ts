// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use server";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api, type Agent, type AgentConfig, type VoiceSession } from "@/lib/api";
import { failure, str, type ActionState } from "@/lib/actions";

const path = (id: string, rest = "") => `/v1/agents/${encodeURIComponent(id)}${rest}`;

export async function createAgentAction(_: ActionState, f: FormData): Promise<ActionState> {
  let saved: Agent;
  try {
    saved = await api<Agent>("/v1/agents", {
      method: "POST",
      body: { name: str(f, "name"), description: str(f, "description"), template_key: str(f, "template_key") || null },
    });
  } catch (e) {
    return failure(e);
  }
  revalidatePath("/app/agents");
  redirect(`/app/agents/${saved.id}`);
}

export type SaveResult = { ok?: string; error?: string; agent?: Agent };

/** Saves the builder. The server writes a new immutable version only when something changed. */
export async function saveAgentAction(
  id: string, body: { name: string; description: string; note: string; config: AgentConfig },
): Promise<SaveResult> {
  try {
    const before = await api<Agent>(path(id));
    const agent = await api<Agent>(path(id), { method: "PUT", body: { ...body, note: body.note || null } });
    revalidatePath(`/app/agents/${id}`);
    revalidatePath("/app/agents");
    if (agent.version === before.version) return { ok: "No changes to save.", agent };
    const live = agent.published_version ? ` Live callers still reach version ${agent.published_version} until you publish.` : "";
    return { ok: `Saved as version ${agent.version}. Test calls use it from now on.${live}`, agent };
  } catch (e) {
    return { error: failure(e)?.error ?? "Could not save." };
  }
}

async function lifecycle(f: FormData, rest: string, body?: Record<string, unknown>): Promise<ActionState> {
  const id = str(f, "id");
  try {
    await api(path(id, rest), { method: "POST", body: body ?? {} });
  } catch (e) {
    return failure(e);
  }
  revalidatePath(`/app/agents/${id}`);
  revalidatePath("/app/agents");
  return { ok: "Done." };
}

export async function publishAction(_: ActionState, f: FormData): Promise<ActionState> {
  const r = await lifecycle(f, "/publish", {
    version_id: str(f, "version_id") || null, skip_test_reason: str(f, "skip_test_reason") || null,
  });
  return r?.ok ? { ok: "Published. New calls use this version; calls already running keep theirs." } : r;
}

export async function rollbackAction(_: ActionState, f: FormData): Promise<ActionState> {
  const r = await lifecycle(f, "/rollback", { version_id: str(f, "version_id"), reason: str(f, "reason") || null });
  return r?.ok ? { ok: "Rolled back. New calls use this version; calls already running keep theirs." } : r;
}

export async function lifecycleAction(_: ActionState, f: FormData): Promise<ActionState> {
  const op = str(f, "op");
  if (!["pause", "resume", "archive", "restore"].includes(op)) return { error: "Unknown action" };
  const r = await lifecycle(f, `/${op}`);
  if (r?.ok && op === "archive") redirect("/app/agents");
  return r;
}

export type StartCallResult = { session?: VoiceSession; error?: string };

export async function startCallAction(
  agentId: string, opts: { versionId?: string; afterHours?: boolean } = {},
): Promise<StartCallResult> {
  try {
    return {
      session: await api<VoiceSession>("/v1/voice/sessions", {
        method: "POST",
        body: { agent_id: agentId, version_id: opts.versionId || null, simulate_after_hours: !!opts.afterHours },
      }),
    };
  } catch (e) {
    const r = failure(e);
    return { error: r?.error ?? "Could not start the call." };
  }
}

export async function endCallAction(callId: string): Promise<void> {
  await api(`/v1/calls/${encodeURIComponent(callId)}/end`, { method: "POST" }).catch(() => undefined);
}
