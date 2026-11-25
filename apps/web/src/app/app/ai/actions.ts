// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use server";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api, ApiError, type AiTest } from "@/lib/api";
import { failure, opt, str, type ActionState } from "@/lib/actions";

async function row(fn: () => Promise<unknown>, okMsg?: string) {
  let msg: string | null = null;
  try {
    await fn();
  } catch (e) {
    if (!(e instanceof ApiError)) throw e;
    msg = e.message;
  }
  revalidatePath("/app/ai");
  redirect(msg ? `/app/ai?error=${encodeURIComponent(msg)}` : okMsg ? `/app/ai?ok=${encodeURIComponent(okMsg)}` : "/app/ai");
}

export async function saveRoutesAction(f: FormData) {
  const kind = str(f, "kind");
  const routes = [0, 1, 2]
    .map((i) => ({ model_id: str(f, `model_${i}`), credential_id: opt(f, `cred_${i}`) }))
    .filter((r) => r.model_id);
  await row(() => api(`/v1/ai/routes/${encodeURIComponent(kind)}`, { method: "PUT", body: { routes } }),
    `Saved ${kind.toUpperCase()} routing.`);
}

export async function addKeyAction(_: ActionState, f: FormData): Promise<ActionState> {
  try {
    await api("/v1/ai/credentials", {
      method: "POST", body: { provider_key: str(f, "provider_key"), label: str(f, "label"), secret: str(f, "secret") },
    });
  } catch (e) {
    return failure(e);
  }
  revalidatePath("/app/ai");
  return { ok: "Key saved. It is encrypted and will never be shown again." };
}

export async function verifyKeyAction(f: FormData) {
  await row(() => api(`/v1/ai/credentials/${encodeURIComponent(str(f, "id"))}/verify`, { method: "POST" }));
}

export async function revokeKeyAction(f: FormData) {
  await row(() => api(`/v1/ai/credentials/${encodeURIComponent(str(f, "id"))}`, { method: "DELETE" }), "Key revoked.");
}

export type TestState = { error?: string; result?: AiTest; detail?: AiTest } | undefined;

function testFailure(e: unknown): TestState {
  if (e instanceof ApiError) {
    const d = e.details as Partial<AiTest> | undefined;
    return { error: e.message, detail: d?.attempts ? (d as AiTest) : undefined };
  }
  if (e && typeof e === "object" && "digest" in e) throw e;
  return { error: "The service is unavailable. Please try again." };
}

export async function testChatAction(_: TestState, f: FormData): Promise<TestState> {
  try {
    return { result: await api<AiTest>("/v1/ai/test/chat", {
      method: "POST", body: { prompt: str(f, "prompt"), system: opt(f, "system"), language: opt(f, "language") } }) };
  } catch (e) {
    return testFailure(e);
  }
}

export async function testSpeechAction(_: TestState, f: FormData): Promise<TestState> {
  try {
    return { result: await api<AiTest>("/v1/ai/test/speech", {
      method: "POST", body: { text: str(f, "text"), language: opt(f, "language"), voice: opt(f, "voice") } }) };
  } catch (e) {
    return testFailure(e);
  }
}

const AUDIO = ["audio/wav", "audio/x-wav", "audio/mpeg", "audio/webm", "audio/ogg"];

export async function testTranscribeAction(_: TestState, f: FormData): Promise<TestState> {
  const file = f.get("audio");
  if (!(file instanceof File) || file.size === 0) return { error: "Choose an audio file." };
  if (file.size > 5 * 1024 * 1024) return { error: "Audio must be 5 MB or smaller." };
  const mime = AUDIO.includes(file.type) ? file.type : "audio/wav";
  const audio_base64 = Buffer.from(await file.arrayBuffer()).toString("base64");
  try {
    return { result: await api<AiTest>("/v1/ai/test/transcribe", {
      method: "POST", body: { audio_base64, mime, language: opt(f, "language") } }) };
  } catch (e) {
    return testFailure(e);
  }
}
