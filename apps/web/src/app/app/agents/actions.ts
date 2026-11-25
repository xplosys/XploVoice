// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use server";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api, type Agent, type AgentConfig, type VoiceSession } from "@/lib/api";
import { failure, str, type ActionState } from "@/lib/actions";

function config(f: FormData): AgentConfig {
  const n = (k: string) => Number(str(f, k));
  return {
    greeting: str(f, "greeting"),
    instructions: str(f, "instructions"),
    language: str(f, "language") as AgentConfig["language"],
    voice: str(f, "voice") || null,
    max_call_seconds: n("max_call_seconds"),
    silence_timeout_seconds: n("silence_timeout_seconds"),
    endpoint_silence_ms: n("endpoint_silence_ms"),
    barge_in_min_ms: n("barge_in_min_ms"),
    interruptible: f.get("interruptible") === "on",
  };
}

export async function saveAgentAction(_: ActionState, f: FormData): Promise<ActionState> {
  const id = str(f, "id");
  let saved: Agent;
  try {
    saved = await api<Agent>(id ? `/v1/agents/${encodeURIComponent(id)}` : "/v1/agents", {
      method: id ? "PUT" : "POST", body: { name: str(f, "name"), config: config(f) },
    });
  } catch (e) {
    return failure(e);
  }
  revalidatePath("/app/agents");
  if (!id) redirect(`/app/agents/${saved.id}`);
  return { ok: `Saved as version ${saved.version}. New calls use it; calls already running keep their version.` };
}

export async function archiveAgentAction(f: FormData) {
  await api(`/v1/agents/${encodeURIComponent(str(f, "id"))}/archive`, { method: "POST" });
  revalidatePath("/app/agents");
  redirect("/app/agents");
}

export type StartCallResult = { session?: VoiceSession; error?: string };

export async function startCallAction(agentId: string): Promise<StartCallResult> {
  try {
    return { session: await api<VoiceSession>("/v1/voice/sessions", { method: "POST", body: { agent_id: agentId } }) };
  } catch (e) {
    const r = failure(e);
    return { error: r?.error ?? "Could not start the call." };
  }
}

export async function endCallAction(callId: string): Promise<void> {
  await api(`/v1/calls/${encodeURIComponent(callId)}/end`, { method: "POST" }).catch(() => undefined);
}
