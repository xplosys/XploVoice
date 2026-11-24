// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import { useActionState } from "react";
import { changePasswordAction, mfaDisableAction, mfaEnrollAction, mfaVerifyAction } from "@/app/app/actions";
import { Button, FormError, Input, Label } from "@/components/ui";
import { ActionForm } from "./action-form";

const Code = () => (
  <div><Label htmlFor="code">6-digit code</Label>
    <Input id="code" name="code" inputMode="numeric" pattern="\d{6}" maxLength={6} autoComplete="one-time-code" required /></div>
);

export function MfaSetup() {
  const [enroll, start, pending] = useActionState(mfaEnrollAction, undefined);
  if (!enroll?.data) {
    return (
      <form action={start} className="space-y-3">
        <p className="text-sm text-slate-600">Use an authenticator app such as Google Authenticator, Microsoft Authenticator or 1Password.</p>
        <FormError message={enroll?.error} />
        <Button type="submit" disabled={pending}>Set up two-factor authentication</Button>
      </form>
    );
  }
  return (
    <div className="space-y-4">
      <div className="rounded-md bg-slate-50 p-3 text-sm">
        <p>In your authenticator app, add an account with this setup key:</p>
        <code className="mt-2 block break-all font-mono text-base tracking-wider">{enroll.data.secret}</code>
        <a href={enroll.data.otpauth_uri} className="mt-2 inline-block text-brand-700 underline">Open in authenticator app</a>
      </div>
      <ActionForm action={mfaVerifyAction} submit="Verify and turn on"><Code /></ActionForm>
    </div>
  );
}

export function MfaDisable() {
  return (
    <ActionForm action={mfaDisableAction} submit="Turn off two-factor" variant="danger">
      <Code />
      <div><Label htmlFor="mfa-pw">Password</Label><Input id="mfa-pw" name="password" type="password" autoComplete="current-password" required /></div>
    </ActionForm>
  );
}

export function PasswordForm() {
  return (
    <ActionForm action={changePasswordAction} submit="Change password">
      <div><Label htmlFor="current_password">Current password</Label>
        <Input id="current_password" name="current_password" type="password" autoComplete="current-password" required /></div>
      <div><Label htmlFor="new_password">New password</Label>
        <Input id="new_password" name="new_password" type="password" autoComplete="new-password" minLength={12} required /></div>
      <p className="text-xs text-slate-500">Changing your password signs you out everywhere, in every organisation.</p>
    </ActionForm>
  );
}
