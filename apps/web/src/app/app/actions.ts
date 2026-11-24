// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use server";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { failure, opt, str, type ActionState } from "@/lib/actions";
import { clearSession, setSession, type Tokens } from "@/lib/session";

export async function switchTenantAction(f: FormData) {
  const t = await api<Tokens>("/v1/auth/switch-tenant", { method: "POST", body: { tenant_id: str(f, "tenant_id") } });
  await setSession(t);
  redirect("/app");
}

export async function acceptExistingAction(_: ActionState, f: FormData): Promise<ActionState> {
  try {
    const t = await api<Tokens>("/v1/invitations/accept", { method: "POST", body: { token: str(f, "token") } });
    await setSession(t);
  } catch (e) {
    return failure(e);
  }
  redirect("/app");
}

export async function updateTenantAction(_: ActionState, f: FormData): Promise<ActionState> {
  try {
    await api("/v1/tenants/current", {
      method: "PATCH",
      body: {
        name: str(f, "name"), timezone: str(f, "timezone"), default_language: str(f, "default_language"),
        business_phone: opt(f, "business_phone"), industry: opt(f, "industry"), website: opt(f, "website"),
      },
    });
  } catch (e) {
    return failure(e);
  }
  revalidatePath("/app", "layout");
  return { ok: "Settings saved." };
}

export async function inviteAction(_: ActionState, f: FormData): Promise<ActionState> {
  try {
    const r = await api<{ email: string; accept_url: string | null }>("/v1/invitations", {
      method: "POST", body: { email: str(f, "email"), role: str(f, "role") },
    });
    revalidatePath("/app/team");
    return {
      ok: `Invitation created for ${r.email}.`,
      data: r.accept_url ? { accept_url: r.accept_url } : undefined,
    };
  } catch (e) {
    return failure(e);
  }
}

// Row actions (plain forms) report failures through the page URL so the message survives production builds.
async function rowAction(fn: () => Promise<unknown>, page: string) {
  let msg: string | null = null;
  try {
    await fn();
  } catch (e) {
    if (!(e instanceof ApiError)) throw e;
    msg = e.message;
  }
  revalidatePath(page);
  if (msg) redirect(`${page}?error=${encodeURIComponent(msg)}`);
}

export async function revokeInviteAction(f: FormData) {
  await rowAction(() => api(`/v1/invitations/${encodeURIComponent(str(f, "id"))}`, { method: "DELETE" }), "/app/team");
}

export async function changeRoleAction(f: FormData) {
  await rowAction(
    () => api(`/v1/members/${encodeURIComponent(str(f, "id"))}`, { method: "PATCH", body: { role: str(f, "role") } }),
    "/app/team",
  );
}

export async function removeMemberAction(f: FormData) {
  await rowAction(() => api(`/v1/members/${encodeURIComponent(str(f, "id"))}`, { method: "DELETE" }), "/app/team");
}

export async function mfaEnrollAction(_: ActionState): Promise<ActionState> {
  try {
    const r = await api<{ secret: string; otpauth_uri: string }>("/v1/auth/mfa/enroll", { method: "POST" });
    return { data: r };
  } catch (e) {
    return failure(e);
  }
}

export async function mfaVerifyAction(_: ActionState, f: FormData): Promise<ActionState> {
  try {
    await api("/v1/auth/mfa/verify", { method: "POST", body: { code: str(f, "code") } });
  } catch (e) {
    return failure(e);
  }
  revalidatePath("/app", "layout");
  return { ok: "Two-factor authentication is on. You will be asked for a code at your next sign-in." };
}

export async function mfaDisableAction(_: ActionState, f: FormData): Promise<ActionState> {
  try {
    await api("/v1/auth/mfa/disable", {
      method: "POST", body: { code: str(f, "code"), password: String(f.get("password") ?? "") },
    });
  } catch (e) {
    return failure(e);
  }
  revalidatePath("/app", "layout");
  return { ok: "Two-factor authentication is off." };
}

export async function changePasswordAction(_: ActionState, f: FormData): Promise<ActionState> {
  try {
    await api("/v1/auth/password", {
      method: "POST",
      body: { current_password: String(f.get("current_password") ?? ""), new_password: String(f.get("new_password") ?? "") },
    });
  } catch (e) {
    return failure(e);
  }
  // Every session, including this one, is revoked server-side. Sign in again with the new password.
  await clearSession();
  redirect("/login?changed=1");
}
