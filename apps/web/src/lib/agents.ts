// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import "server-only";
import { api, type AgentStatus, type AiProvider, type KindRoutes } from "./api";
import type { ModelOptions } from "@/components/forms/agent-builder";

/** Models an agent may choose: the tenant's routed models (or the platform defaults), with their voices. */
export async function modelOptions(): Promise<ModelOptions> {
  const [routes, catalog] = await Promise.all([api<KindRoutes[]>("/v1/ai/routes"), api<AiProvider[]>("/v1/ai/catalog")]);
  const voices = new Map(catalog.flatMap((p) => p.models.map((m) => [m.id, m.voices] as const)));
  const out: ModelOptions = { llm: [], stt: [], tts: [] };
  for (const k of routes) {
    out[k.kind] = k.routes.map((r) => ({ id: r.model_id, label: `${r.provider} · ${r.model}`, voices: voices.get(r.model_id) ?? [] }));
  }
  return out;
}

export const STATUS: Record<AgentStatus, { label: string; tone: "slate" | "green" | "amber" | "red" | "brand" }> = {
  draft: { label: "Draft", tone: "slate" },
  testing: { label: "Testing", tone: "brand" },
  published: { label: "Published", tone: "green" },
  paused: { label: "Paused", tone: "amber" },
  archived: { label: "Archived", tone: "red" },
};

export const LANG: Record<string, string> = {
  "en-IN": "English (India)", "hi-IN": "Hindi", "hi-Latn-IN": "Hinglish", "en-US": "English (US)",
};

/** Flattens a config into dotted paths, for comparing two versions. */
export function flatten(o: unknown, prefix = ""): Record<string, string> {
  if (o === null || typeof o !== "object" || Array.isArray(o)) return { [prefix]: JSON.stringify(o) };
  return Object.entries(o as Record<string, unknown>).reduce<Record<string, string>>(
    (acc, [k, v]) => ({ ...acc, ...flatten(v, prefix ? `${prefix}.${k}` : k) }), {});
}
