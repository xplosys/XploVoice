// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
// Tokens live only in httpOnly cookies set by the server (BFF pattern). Browser JavaScript never sees them.
import "server-only";
import { cookies } from "next/headers";

export const ACCESS_COOKIE = "xv_at";
export const REFRESH_COOKIE = "xv_rt";

export type Tokens = { access_token: string; refresh_token: string; access_expires_at: string; tenant_id: string };

const secure = process.env.NODE_ENV === "production";

export async function setSession(t: Tokens) {
  const jar = await cookies();
  jar.set(ACCESS_COOKIE, t.access_token, {
    httpOnly: true, secure, sameSite: "lax", path: "/", expires: new Date(t.access_expires_at),
  });
  jar.set(REFRESH_COOKIE, t.refresh_token, {
    httpOnly: true, secure, sameSite: "lax", path: "/", maxAge: 60 * 60 * 24 * 30,
  });
}

export async function clearSession() {
  const jar = await cookies();
  jar.delete(ACCESS_COOKIE);
  jar.delete(REFRESH_COOKIE);
}

export async function accessToken(): Promise<string | undefined> {
  return (await cookies()).get(ACCESS_COOKIE)?.value;
}
