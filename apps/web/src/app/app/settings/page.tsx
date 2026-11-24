// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import { api, type Country, type Tenant } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { Card } from "@/components/ui";
import { SettingsForm } from "@/components/forms/settings-form";

export const metadata = { title: "Organisation · XploVoice" };

export default async function SettingsPage() {
  const me = await getMe();
  const [t, countries] = await Promise.all([
    api<Tenant>("/v1/tenants/current"),
    api<Country[]>("/v1/reference/countries", { auth: false }),
  ]);
  const country = countries.find((c) => c.code === t.country_code)!;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Organisation</h1>
      <Card>
        <dl className="grid gap-4 text-sm sm:grid-cols-4">
          <div><dt className="text-slate-500">Country</dt><dd className="font-medium">{country.name}</dd></div>
          <div><dt className="text-slate-500">Currency</dt><dd className="font-medium">{t.currency}</dd></div>
          <div><dt className="text-slate-500">Date format</dt><dd className="font-medium">{t.date_format}</dd></div>
          <div><dt className="text-slate-500">Workspace ID</dt><dd className="font-medium">{t.slug}</dd></div>
        </dl>
        <p className="mt-3 text-xs text-slate-500">Country and currency are fixed at sign-up because billing and data residency depend on them.</p>
      </Card>
      <Card>
        {can(me, "tenant:manage") ? <SettingsForm t={t} country={country} /> : (
          <p className="text-sm text-slate-600">Only owners and admins can change organisation settings.</p>
        )}
      </Card>
    </div>
  );
}
