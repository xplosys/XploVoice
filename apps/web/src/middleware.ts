// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
// Refreshes the short-lived access token before protected pages render, and guards /app and /admin.
import { NextResponse, type NextRequest } from "next/server";

const API = process.env.XV_API_INTERNAL_URL ?? "http://localhost:8000";

function expiresSoon(jwt: string | undefined): boolean {
  if (!jwt) return true;
  try {
    const payload = JSON.parse(atob(jwt.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload.exp * 1000 - Date.now() < 60_000;
  } catch {
    return true;
  }
}

export async function middleware(req: NextRequest) {
  const at = req.cookies.get("xv_at")?.value;
  const rt = req.cookies.get("xv_rt")?.value;
  const login = new URL(`/login?next=${encodeURIComponent(req.nextUrl.pathname + req.nextUrl.search)}`, req.url);
  if (!expiresSoon(at)) return NextResponse.next();
  if (!rt) return NextResponse.redirect(login);

  const r = await fetch(`${API}/v1/auth/refresh`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: rt }),
  }).catch(() => null);
  if (!r || !r.ok) {
    const res = NextResponse.redirect(login);
    res.cookies.delete("xv_at");
    res.cookies.delete("xv_rt");
    return res;
  }
  const t = await r.json();
  // Forward the new token to this request's server components, and store it in the browser.
  const headers = new Headers(req.headers);
  headers.set("cookie", `xv_at=${t.access_token}; xv_rt=${t.refresh_token}`);
  const res = NextResponse.next({ request: { headers } });
  const secure = process.env.NODE_ENV === "production";
  res.cookies.set("xv_at", t.access_token, { httpOnly: true, secure, sameSite: "lax", path: "/",
    expires: new Date(t.access_expires_at) });
  res.cookies.set("xv_rt", t.refresh_token, { httpOnly: true, secure, sameSite: "lax", path: "/",
    maxAge: 60 * 60 * 24 * 30 });
  return res;
}

export const config = { matcher: ["/app/:path*", "/admin/:path*"] };
