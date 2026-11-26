// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import type { ReactNode } from "react";
import { api, type MyTenant } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { Copyright, Logo } from "@/components/brand";
import { SideNav, type NavItem } from "@/components/nav";
import { Badge, Button, Select } from "@/components/ui";
import { logoutAction } from "@/app/(auth)/actions";
import { switchTenantAction } from "./actions";

export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const me = await getMe();
  const tenants = await api<MyTenant[]>("/v1/tenants/mine").catch(() => [] as MyTenant[]);
  const items: NavItem[] = [
    { href: "/app", label: "Overview" },
    ...(can(me, "members:read") ? [{ href: "/app/team", label: "Team" }] : []),
    { href: "/app/settings", label: "Organisation" },
    { href: "/app/security", label: "Security" },
    ...(can(me, "audit:read") ? [{ href: "/app/audit", label: "Audit log" }] : []),
    ...(can(me, "ai:read") ? [{ href: "/app/ai", label: "AI providers" }] : []),
    ...(can(me, "ai:test") ? [{ href: "/app/ai/playground", label: "AI playground" }] : []),
    ...(can(me, "usage:read") ? [{ href: "/app/usage", label: "Usage" }] : []),
    ...(can(me, "agents:read") ? [{ href: "/app/agents", label: "Voice agents" }] : []),
    ...(can(me, "calls:read") ? [{ href: "/app/calls", label: "Calls" }] : []),
    ...(can(me, "knowledge:read") ? [{ href: "/app/knowledge", label: "Knowledge base" }] : []),
    ...(can(me, "workflows:read") ? [{ href: "/app/appointments", label: "Appointments" }, { href: "/app/leads", label: "Leads" },
      { href: "/app/follow-ups", label: "Follow-ups" }] : []),
    ...(can(me, "support:read") ? [{ href: "/app/tickets", label: "Tickets" }, { href: "/app/notifications", label: "Messages" }] : []),
    ...(can(me, "agents:read") ? [{ href: "/app/tools", label: "Business tools" }] : []),
    ...(can(me, "tenant:read") ? [{ href: "/app/integrations", label: "Integrations" }] : []),
    ...(can(me, "telephony:read") ? [{ href: "/app/numbers", label: "Phone numbers" }] : []),
    ...(can(me, "campaigns:read") ? [{ href: "/app/campaigns", label: "Campaigns" }] : []),
    ...(can(me, "consent:read") ? [{ href: "/app/do-not-call", label: "Do not call" }] : []),
    { href: "/app/billing", label: "Billing", phase: 7 },
  ];
  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white p-4 md:flex">
        <div className="mb-6"><Logo href="/app" /></div>
        {tenants.length > 1 && (
          <form action={switchTenantAction} className="mb-4 flex gap-2">
            <Select name="tenant_id" defaultValue={me.tenant_id} aria-label="Switch organisation">
              {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.name}</option>)}
            </Select>
            <Button type="submit" variant="secondary" className="px-2">Go</Button>
          </form>
        )}
        <SideNav items={items} />
        <div className="mt-auto pt-6"><Copyright /></div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-4 border-b border-slate-200 bg-white px-6 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="truncate font-medium">{me.tenant_name}</span>
            <Badge tone="brand">{me.role.replace("_", " ")}</Badge>
          </div>
          <div className="flex items-center gap-3 text-sm">
            {me.is_platform_admin && <Link href="/admin" className="text-brand-700 underline">Platform admin</Link>}
            <span className="hidden text-slate-600 sm:inline">{me.display_name}</span>
            <form action={logoutAction}><Button variant="ghost" type="submit">Sign out</Button></form>
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
