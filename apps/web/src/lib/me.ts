// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import "server-only";
import { cache } from "react";
import { redirect } from "next/navigation";
import { api, ApiError, type Me } from "./api";

/** The signed-in user for this request. Redirects to sign-in when the session is missing or revoked. */
export const getMe = cache(async (): Promise<Me> => {
  try {
    return await api<Me>("/v1/auth/me");
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) redirect("/login");
    throw e;
  }
});

export const can = (me: Me, perm: string) => me.permissions.includes(perm);
