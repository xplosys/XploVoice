// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import { useActionState } from "react";
import { acceptNewAction } from "@/app/(auth)/actions";
import { Button, FormError, Input, Label } from "@/components/ui";

export function AcceptForm({ token }: { token: string }) {
  const [state, action, pending] = useActionState(acceptNewAction, undefined);
  return (
    <form action={action} className="space-y-4">
      <input type="hidden" name="token" value={token} />
      <div><Label htmlFor="display_name">Your name</Label><Input id="display_name" name="display_name" required maxLength={120} /></div>
      <div><Label htmlFor="password">Choose a password</Label>
        <Input id="password" name="password" type="password" autoComplete="new-password" minLength={12} required /></div>
      <FormError message={state?.error} />
      <Button type="submit" className="w-full" disabled={pending}>{pending ? "Joining…" : "Create account and join"}</Button>
    </form>
  );
}
