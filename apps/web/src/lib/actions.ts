// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
// Shared result shape for server actions so forms can render errors and success uniformly.
import { ApiError } from "./api";

export type ActionState = { error?: string; ok?: string; data?: Record<string, string> } | undefined;

export function failure(e: unknown): ActionState {
  if (e instanceof ApiError) return { error: e.message };
  // Re-throw Next.js control flow (redirect / notFound) so it is not swallowed.
  if (e && typeof e === "object" && "digest" in e) throw e;
  return { error: "The service is unavailable. Please try again." };
}

export const str = (f: FormData, k: string) => String(f.get(k) ?? "").trim();
export const opt = (f: FormData, k: string) => str(f, k) || null;
