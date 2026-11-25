// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import { getMe } from "@/lib/me";
import { Badge, Card } from "@/components/ui";
import { MfaDisable, MfaSetup, PasswordForm } from "@/components/forms/security-forms";

export const metadata = { title: "Security · XploVoice" };

const DONE: Record<string, string> = {
  on: "Two-factor authentication is on. You will be asked for a code each time you sign in.",
  off: "Two-factor authentication is off.",
};

export default async function SecurityPage({ searchParams }: { searchParams: Promise<{ mfa?: string }> }) {
  const me = await getMe();
  const done = DONE[(await searchParams).mfa ?? ""];
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Security</h1>
      {done && <p role="status" className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{done}</p>}
      <Card>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-medium">Two-factor authentication</h2>
          {me.mfa_enabled ? <Badge tone="green">On</Badge> : <Badge tone="amber">Off</Badge>}
        </div>
        {me.mfa_enabled ? <MfaDisable /> : <MfaSetup />}
      </Card>
      <Card><h2 className="mb-4 font-medium">Password</h2><PasswordForm /></Card>
    </div>
  );
}
