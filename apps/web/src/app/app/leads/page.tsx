// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type Lead } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { ActionForm } from "@/components/forms/action-form";
import { Badge, Card, Input, Label } from "@/components/ui";
import { LEAD_TONE } from "@/lib/tones";
import { createLeadAction } from "../workflow-actions";
import { When } from "@/components/when";

export const metadata = { title: "Leads · XploVoice" };

const STATUSES = ["new", "contacted", "qualified", "won", "lost"] as const;

export default async function LeadsPage({ searchParams }: { searchParams: Promise<{ status?: string }> }) {
  const me = await getMe();
  if (!can(me, "workflows:read")) redirect("/app");
  const { status } = await searchParams;
  const leads = await api<Lead[]>(`/v1/leads${status ? `?status=${encodeURIComponent(status)}` : ""}`);
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Leads</h1>
        <p className="text-sm text-slate-600">People who showed interest on a call, or that your team added. The score counts 25 each for a stated need, budget, timeline and a way to reach them.</p>
      </div>
      <nav className="flex flex-wrap gap-2 text-sm">
        {[undefined, ...STATUSES].map((s) => (
          <Link key={s ?? "all"} href={s ? `/app/leads?status=${s}` : "/app/leads"}
            className={`rounded-full border px-3 py-1 ${status === s ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-300"}`}>{s ?? "all"}</Link>
        ))}
      </nav>
      <Card className="p-0">
        {leads.length === 0 ? <p className="p-6 text-sm text-slate-600">No leads yet.</p> : (
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 text-left text-xs uppercase text-slate-500">
              <tr><th className="px-6 py-2">Name</th><th className="px-3 py-2">Interest</th><th className="px-3 py-2">Score</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">From</th><th className="px-3 py-2">Added</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {leads.map((l) => (
                <tr key={l.id}>
                  <td className="px-6 py-2"><Link className="font-medium text-brand-700 underline" href={`/app/leads/${l.id}`}>{l.name}</Link>{l.company && <span className="text-slate-500"> · {l.company}</span>}</td>
                  <td className="max-w-xs truncate px-3 py-2">{l.interest || "–"}</td>
                  <td className="px-3 py-2">{l.score ?? "–"}</td>
                  <td className="px-3 py-2"><Badge tone={LEAD_TONE[l.status]}>{l.status}</Badge></td>
                  <td className="px-3 py-2">{l.source}</td>
                  <td className="px-3 py-2 text-slate-500"><When iso={l.created_at} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {can(me, "workflows:manage") && (
        <Card>
          <h2 className="mb-3 font-medium">Add a lead</h2>
          <ActionForm action={createLeadAction} submit="Add lead">
            <div className="grid gap-3 sm:grid-cols-3">
              <div><Label htmlFor="name">Name</Label><Input id="name" name="name" required maxLength={120} /></div>
              <div><Label htmlFor="phone">Phone</Label><Input id="phone" name="phone" maxLength={30} /></div>
              <div><Label htmlFor="email">Email</Label><Input id="email" name="email" type="email" maxLength={200} /></div>
              <div><Label htmlFor="company">Company</Label><Input id="company" name="company" maxLength={200} /></div>
              <div><Label htmlFor="budget">Budget</Label><Input id="budget" name="budget" maxLength={200} /></div>
              <div><Label htmlFor="timeline">Timeline</Label><Input id="timeline" name="timeline" maxLength={200} /></div>
            </div>
            <div><Label htmlFor="interest">What they need</Label><Input id="interest" name="interest" maxLength={1000} /></div>
          </ActionForm>
        </Card>
      )}
    </div>
  );
}
