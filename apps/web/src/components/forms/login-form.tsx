// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import Link from "next/link";
import { useActionState, useState } from "react";
import { loginAction } from "@/app/(auth)/actions";
import { Button, FormError, Input, Label } from "@/components/ui";

export function LoginForm({ next }: { next: string }) {
  const [state, action, pending] = useActionState(loginAction, undefined);
  const needMfa = state?.data?.mfa === "1";
  // Controlled so the values survive the form reset React performs after each action (the 2FA step re-submits them).
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  return (
    <form action={action} className="space-y-4">
      <input type="hidden" name="next" value={next} />
      <div><Label htmlFor="email">Work email</Label><Input id="email" name="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
      <div><Label htmlFor="password">Password</Label><Input id="password" name="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></div>
      {needMfa && (
        <div><Label htmlFor="mfa_code">Authenticator code</Label>
          <Input id="mfa_code" name="mfa_code" inputMode="numeric" pattern="\d{6}" maxLength={6} autoComplete="one-time-code" autoFocus required /></div>
      )}
      <FormError message={state?.error} />
      <Button type="submit" className="w-full" disabled={pending}>{pending ? "Signing in…" : "Sign in"}</Button>
      <p className="text-center text-sm text-slate-600">New to XploVoice? <Link className="text-brand-700 underline" href="/register">Create an account</Link></p>
    </form>
  );
}
