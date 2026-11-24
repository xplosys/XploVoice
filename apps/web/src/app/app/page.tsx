// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { api, type Tenant } from "@/lib/api";
import { getMe } from "@/lib/me";
import { Badge, Card, Notice } from "@/components/ui";

export const metadata = { title: "Overview · XploVoice" };

export default async function Overview() {
  const me = await getMe();
  const t = await api<Tenant>("/v1/tenants/current");
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Welcome, {me.display_name}</h1>
      {!me.mfa_enabled && (
        <Notice>Protect your account with two-factor authentication. <Link className="underline" href="/app/security">Turn it on</Link>.</Notice>
      )}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card><p className="text-sm text-slate-500">Region</p><p className="mt-1 text-lg font-medium">{t.country_code === "IN" ? "India" : "United States"}</p></Card>
        <Card><p className="text-sm text-slate-500">Currency</p><p className="mt-1 text-lg font-medium">{t.currency}</p></Card>
        <Card><p className="text-sm text-slate-500">Time zone</p><p className="mt-1 text-lg font-medium">{t.timezone}</p></Card>
      </div>
      <Card>
        <h2 className="mb-3 font-medium">What is available now</h2>
        <ul className="space-y-2 text-sm text-slate-700">
          <li className="flex justify-between"><span>Workspace, team and roles</span><Badge tone="green">Available</Badge></li>
          <li className="flex justify-between"><span>Two-factor sign-in and audit log</span><Badge tone="green">Available</Badge></li>
          <li className="flex justify-between"><span>AI provider keys and usage metering</span><Badge>Phase 2</Badge></li>
          <li className="flex justify-between"><span>Voice agent builder and test calls</span><Badge>Phase 3–4</Badge></li>
          <li className="flex justify-between"><span>Phone numbers and live calls</span><Badge>Phase 6</Badge></li>
        </ul>
      </Card>
    </div>
  );
}
