// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import { Card } from "@/components/ui";
import { LoginForm } from "@/components/forms/login-form";

export const metadata = { title: "Sign in · XploVoice" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string; changed?: string }> }) {
  const { next, changed } = await searchParams;
  return (
    <Card>
      <h1 className="mb-6 text-xl font-semibold">Sign in</h1>
      {changed && <p className="mb-4 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">Password changed. Sign in with your new password.</p>}
      <LoginForm next={next ?? "/app"} />
    </Card>
  );
}
