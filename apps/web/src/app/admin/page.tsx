// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { getMe } from "@/lib/me";
import { Copyright, Logo } from "@/components/brand";
import { ThemePicker } from "@/components/theme-picker";
import { Badge, Button, Card, FormError, Input } from "@/components/ui";
import { reactivateAction, suspendAction } from "./actions";

export const metadata = { title: "Platform admin · XploVoice" };
export const dynamic = "force-dynamic";

type Row = { id: string; name: string; slug: string; country_code: string; currency: string; status: string; members: number; created_at: string };

export default async function AdminPage({ searchParams }: { searchParams: Promise<{ q?: string; error?: string }> }) {
  await getMe();
  const { q, error } = await searchParams;
  let rows: Row[] = [];
  let denied: string | null = null;
  try {
    rows = await api<Row[]>(`/admin/v1/tenants${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 403) throw e;
    denied = e.message;
  }
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-3"><Logo href="/admin" /><Badge tone="red">Platform admin</Badge></div>
        <nav className="flex items-center gap-4 text-sm"><Link href="/admin/ai" className="text-brand-700 underline">AI catalog</Link><Link href="/admin/billing" className="text-brand-700 underline">Billing</Link><Link href="/admin/healthcare" className="text-brand-700 underline">Healthcare</Link><Link href="/app" className="text-brand-700 underline">Back to workspace</Link><ThemePicker /></nav>
      </header>
      <main className="mx-auto max-w-6xl space-y-6 p-6">
        <h1 className="text-2xl font-semibold">Tenants</h1>
        <p className="text-sm text-slate-600">Every view and change here is recorded in the platform audit log. Tenant content (calls, transcripts, knowledge) is not accessible from this console.</p>
        {denied ? <FormError message={`${denied}. Platform administration needs a platform admin account signed in with two-factor authentication.`} /> : (
          <>
            <FormError message={error} />
            <form className="flex max-w-md gap-2"><Input name="q" defaultValue={q} placeholder="Search by name" /><Button variant="secondary" type="submit">Search</Button></form>
            <Card className="overflow-x-auto p-0">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-200 text-slate-500"><tr>
                  <th className="px-4 py-3 font-medium">Tenant</th><th className="px-4 py-3 font-medium">Region</th>
                  <th className="px-4 py-3 font-medium">Members</th><th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Action (reason required)</th></tr></thead>
                <tbody>
                  {rows.map((t) => (
                    <tr key={t.id} className="border-b border-slate-100 last:border-0">
                      <td className="px-4 py-3"><div className="font-medium">{t.name}</div><div className="text-slate-500">{t.slug}</div></td>
                      <td className="px-4 py-3">{t.country_code} · {t.currency}</td>
                      <td className="px-4 py-3">{t.members}</td>
                      <td className="px-4 py-3"><Badge tone={t.status === "active" ? "green" : "red"}>{t.status}</Badge></td>
                      <td className="px-4 py-3">
                        <form action={t.status === "active" ? suspendAction : reactivateAction} className="flex gap-2">
                          <input type="hidden" name="id" value={t.id} />
                          <Input name="reason" required minLength={5} maxLength={500} placeholder="Reason" aria-label={`Reason for ${t.name}`} />
                          <Button type="submit" variant={t.status === "active" ? "danger" : "secondary"}>
                            {t.status === "active" ? "Suspend" : "Reactivate"}
                          </Button>
                        </form>
                      </td>
                    </tr>
                  ))}
                  {rows.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-500">No tenants found.</td></tr>}
                </tbody>
              </table>
            </Card>
          </>
        )}
        <Copyright />
      </main>
    </div>
  );
}
