// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use server";
import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { failure, opt, str, type ActionState } from "@/lib/actions";
import { clearSession, setSession, type Tokens } from "@/lib/session";

function safeNext(n: string): string {
  // Only same-site paths under the signed-in areas; blocks open redirects such as //evil.example.
  return /^\/(app|admin)(\/|\?|$)/.test(n) ? n : "/app";
}

export async function loginAction(_: ActionState, f: FormData): Promise<ActionState> {
  try {
    const t = await api<Tokens>("/v1/auth/login", {
      method: "POST", auth: false,
      body: { email: str(f, "email"), password: String(f.get("password") ?? ""), mfa_code: opt(f, "mfa_code") },
    });
    await setSession(t);
  } catch (e) {
    if (e instanceof ApiError && e.code === "mfa_required") return { error: e.message, data: { mfa: "1" } };
    return failure(e);
  }
  redirect(safeNext(str(f, "next")));
}

export async function registerAction(_: ActionState, f: FormData): Promise<ActionState> {
  try {
    const t = await api<Tokens>("/v1/auth/register", {
      method: "POST", auth: false,
      body: {
        email: str(f, "email"), password: String(f.get("password") ?? ""), display_name: str(f, "display_name"),
        organization_name: str(f, "organization_name"), country_code: str(f, "country_code"),
        timezone: opt(f, "timezone"),
      },
    });
    await setSession(t);
  } catch (e) {
    return failure(e);
  }
  redirect("/app");
}

export async function acceptNewAction(_: ActionState, f: FormData): Promise<ActionState> {
  try {
    const t = await api<Tokens>("/v1/invitations/accept-new", {
      method: "POST", auth: false,
      body: { token: str(f, "token"), display_name: str(f, "display_name"), password: String(f.get("password") ?? "") },
    });
    await setSession(t);
  } catch (e) {
    return failure(e);
  }
  redirect("/app");
}

export async function logoutAction() {
  await api("/v1/auth/logout", { method: "POST" }).catch(() => undefined);
  await clearSession();
  redirect("/login");
}
