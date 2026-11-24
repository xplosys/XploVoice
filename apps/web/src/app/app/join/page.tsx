// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import { getMe } from "@/lib/me";
import { Card, FormError } from "@/components/ui";
import { JoinForm } from "@/components/forms/join-form";

export const metadata = { title: "Accept invitation · XploVoice" };

export default async function JoinPage({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const me = await getMe();
  const { token } = await searchParams;
  return (
    <Card className="max-w-lg">
      <h1 className="mb-2 text-xl font-semibold">Accept invitation</h1>
      {token ? (
        <><p className="mb-4 text-sm text-slate-600">You are signed in as {me.email}. The invitation must be addressed to this email.</p>
          <JoinForm token={token} /></>
      ) : <FormError message="This invitation link is incomplete." />}
    </Card>
  );
}
