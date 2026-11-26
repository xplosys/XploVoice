// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { api, ApiError, type LeadDetail } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { LEAD_TONE, label } from "@/lib/tones";
import { ActionForm } from "@/components/forms/action-form";
import { TzOffset } from "@/components/forms/phase5";
import { Badge, Card, Input, Label, Select } from "@/components/ui";
import { addFollowUpAction, followUpAction, leadNoteAction, leadStatusAction } from "../../workflow-actions";
import { When } from "@/components/when";

export const metadata = { title: "Lead · XploVoice" };

export default async function LeadPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await getMe();
  if (!can(me, "workflows:read")) redirect("/app");
  const { id } = await params;
  const lead = await api<LeadDetail>(`/v1/leads/${encodeURIComponent(id)}`).catch((e) => {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) notFound();
    throw e;
  });
  const manage = can(me, "workflows:manage");
  const facts: [string, string | null][] = [["Phone", lead.phone], ["Email", lead.email], ["Company", lead.company],
    ["Need", lead.interest], ["Budget", lead.budget], ["Timeline", lead.timeline]];
  return (
    <div className="space-y-6">
      <div>
        <Link href="/app/leads" className="text-sm text-brand-700 underline">All leads</Link>
        <h1 className="mt-1 flex items-center gap-3 text-2xl font-semibold">{lead.name} <Badge tone={LEAD_TONE[lead.status]}>{lead.status}</Badge></h1>
        <p className="text-sm text-slate-600">Score {lead.score ?? "–"} · from {lead.source}{lead.call_id && <> · <Link className="underline" href={`/app/calls/${lead.call_id}`}>call record</Link></>} · added <When iso={lead.created_at} /></p>
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <Card>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            {facts.map(([k, v]) => <div key={k}><dt className="text-xs text-slate-500">{k}</dt><dd>{v || "–"}</dd></div>)}
          </dl>
          <h2 className="mb-2 mt-6 font-medium">Activity</h2>
          <ol className="space-y-2 text-sm">
            {lead.activities.length === 0 && <li className="text-slate-600">Nothing yet.</li>}
            {lead.activities.map((a, i) => (
              <li key={i} className="rounded-md border border-slate-200 p-2">
                <p className="text-xs text-slate-500">{label(a.kind)} · <When iso={a.created_at} />{a.call_id && <> · <Link className="underline" href={`/app/calls/${a.call_id}`}>call</Link></>}</p>
                <p className="whitespace-pre-wrap">{a.body}</p>
              </li>
            ))}
          </ol>
          {manage && <div className="mt-4 border-t border-slate-200 pt-4">
            <ActionForm action={leadNoteAction} submit="Add note">
              <input type="hidden" name="id" value={lead.id} />
              <div><Label htmlFor="body">Note</Label><Input id="body" name="body" required maxLength={2000} /></div>
              <div><Label htmlFor="kind">Kind</Label><Select id="kind" name="kind"><option value="note">Note</option><option value="call">Call I made</option></Select></div>
            </ActionForm>
          </div>}
        </Card>
        <div className="space-y-6">
          {manage && <Card>
            <h2 className="mb-2 font-medium">Status</h2>
            <ActionForm key={lead.status} action={leadStatusAction} submit="Update">
              <input type="hidden" name="id" value={lead.id} />
              <Select aria-label="Status" name="status" defaultValue={lead.status}>{["new", "contacted", "qualified", "won", "lost"].map((s) => <option key={s}>{s}</option>)}</Select>
            </ActionForm>
          </Card>}
          <Card>
            <h2 className="mb-2 font-medium">Follow-ups</h2>
            <ul className="mb-3 space-y-2 text-sm">
              {lead.follow_ups.length === 0 && <li className="text-slate-600">None.</li>}
              {lead.follow_ups.map((f) => (
                <li key={f.id} className="flex items-start justify-between gap-2">
                  <span><When iso={f.due_at} /> · {f.channel}{f.note && <span className="block text-xs text-slate-500">{f.note}</span>}</span>
                  {f.status === "open" && manage ? <ActionForm action={followUpAction} submit="Done" variant="ghost" className="">
                    <input type="hidden" name="id" value={f.id} /><input type="hidden" name="lead_id" value={lead.id} /><input type="hidden" name="status" value="done" />
                  </ActionForm> : <Badge>{f.status}</Badge>}
                </li>
              ))}
            </ul>
            {manage && <ActionForm action={addFollowUpAction} submit="Add follow-up">
              <input type="hidden" name="lead_id" value={lead.id} /><TzOffset />
              <div><Label htmlFor="due">When</Label><Input id="due" name="due_at" type="datetime-local" required /></div>
              <div><Label htmlFor="ch">How</Label><Select id="ch" name="channel">{["call", "sms", "email", "task"].map((c) => <option key={c}>{c}</option>)}</Select></div>
              <div><Label htmlFor="fnote">Note</Label><Input id="fnote" name="note" maxLength={500} /></div>
            </ActionForm>}
          </Card>
        </div>
      </div>
    </div>
  );
}
