// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { api, type Country } from "@/lib/api";
import { Card, FormError } from "@/components/ui";
import { RegisterForm } from "@/components/forms/register-form";

export const metadata = { title: "Create account · XploVoice" };
export const dynamic = "force-dynamic";

export default async function RegisterPage() {
  const countries = await api<Country[]>("/v1/reference/countries", { auth: false }).catch(() => null);
  return (
    <Card>
      <h1 className="mb-1 text-xl font-semibold">Create your workspace</h1>
      <p className="mb-6 text-sm text-slate-600">You will be the owner of a new XploVoice tenant.</p>
      {countries ? <RegisterForm countries={countries} /> : <FormError message="The service is unavailable. Please try again." />}
      <p className="mt-4 text-center text-sm text-slate-600">Already have an account? <Link className="text-brand-700 underline" href="/login">Sign in</Link></p>
    </Card>
  );
}
