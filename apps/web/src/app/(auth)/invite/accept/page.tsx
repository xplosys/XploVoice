// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { Card, FormError } from "@/components/ui";
import { AcceptForm } from "@/components/forms/accept-form";

export const metadata = { title: "Accept invitation · XploVoice" };

export default async function AcceptPage({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token } = await searchParams;
  return (
    <Card>
      <h1 className="mb-1 text-xl font-semibold">Join your team on XploVoice</h1>
      {!token ? <FormError message="This invitation link is incomplete." /> : (
        <>
          <p className="mb-6 text-sm text-slate-600">New to XploVoice? Create your account below. Your email comes from the invitation.</p>
          <AcceptForm token={token} />
          <p className="mt-4 text-center text-sm text-slate-600">
            Already have an account?{" "}
            <Link className="text-brand-700 underline" href={`/app/join?token=${encodeURIComponent(token)}`}>Sign in to accept</Link>
          </p>
        </>
      )}
    </Card>
  );
}
