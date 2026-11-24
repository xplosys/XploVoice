// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import { acceptExistingAction } from "@/app/app/actions";
import { ActionForm } from "./action-form";

export function JoinForm({ token }: { token: string }) {
  return <ActionForm action={acceptExistingAction} submit="Accept invitation"><input type="hidden" name="token" value={token} /></ActionForm>;
}
