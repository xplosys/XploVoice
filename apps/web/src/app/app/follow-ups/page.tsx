// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type FollowUp } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { ActionForm } from "@/components/forms/action-form";
import { TzOffset } from "@/components/forms/phase5";
import { Badge, Card, Input, Label, Select } from "@/components/ui";
import { addFollowUpAction, followUpAction } from "../workflow-actions";

export const metadata = { title: "Follow-ups · XploVoice" };

export default async function FollowUpsPage({ searchParams }: { searchParams: Promise<{ status?: string }> }) {
  const me = await getMe();
  if (!can(me, "workflows:read")) redirect("/app");
  const { status = "open" } = await searchParams;
  const items = await api<FollowUp[]>(`/v1/follow-ups?status=${status === "all" ? "" : encodeURIComponent(status)}`);
  const manage = can(me, "workflows:manage");
  const now = Date.now();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Follow-ups</h1>
        <p className="text-sm text-slate-600">Things to do after a call: call someone back, send details, check in. Agents add these when a caller asks to be called back.</p>
      </div>
      <nav className="flex gap-2 text-sm">
        {["open", "done", "cancelled", "all"].map((s) => (
          <Link key={s} href={`/app/follow-ups?status=${s}`} className={`rounded-full border px-3 py-1 ${status === s ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-300"}`}>{s}</Link>
        ))}
      </nav>
      <Card className="p-0">
        {items.length === 0 ? <p className="p-6 text-sm text-slate-600">Nothing here.</p> : (
          <ul className="divide-y divide-slate-100 text-sm">
            {items.map((f) => {
              const late = f.status === "open" && new Date(f.due_at).getTime() < now;
              return (
                <li key={f.id} className="flex flex-wrap items-center justify-between gap-3 px-6 py-3">
                  <div>
                    <p className="font-medium">{new Date(f.due_at).toLocaleString()} · {f.channel} {late && <Badge tone="red">overdue</Badge>}</p>
                    <p className="text-slate-600">{f.note || "–"}
                      {f.lead_id && <> · <Link className="underline" href={`/app/leads/${f.lead_id}`}>{f.lead_name ?? "lead"}</Link></>}
                      {f.ticket_id && <> · <Link className="underline" href={`/app/tickets/${f.ticket_id}`}>ticket</Link></>}
                      {f.call_id && <> · <Link className="underline" href={`/app/calls/${f.call_id}`}>call</Link></>} · from {f.source}</p>
                  </div>
                  {manage && f.status === "open" ? (
                    <div className="flex gap-2">
                      {(["done", "cancelled"] as const).map((s) => (
                        <ActionForm key={s} action={followUpAction} submit={s === "done" ? "Done" : "Cancel"} variant="ghost" className="">
                          <input type="hidden" name="id" value={f.id} /><input type="hidden" name="lead_id" value={f.lead_id ?? ""} /><input type="hidden" name="status" value={s} />
                        </ActionForm>
                      ))}
                    </div>
                  ) : <Badge>{f.status}</Badge>}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
      {manage && (
        <Card>
          <h2 className="mb-3 font-medium">Add a follow-up</h2>
          <ActionForm action={addFollowUpAction} submit="Add">
            <TzOffset />
            <div className="grid gap-3 sm:grid-cols-3">
              <div><Label htmlFor="due">When</Label><Input id="due" name="due_at" type="datetime-local" required /></div>
              <div><Label htmlFor="ch">How</Label><Select id="ch" name="channel">{["call", "sms", "email", "task"].map((c) => <option key={c}>{c}</option>)}</Select></div>
              <div><Label htmlFor="note">Note</Label><Input id="note" name="note" maxLength={500} /></div>
            </div>
          </ActionForm>
        </Card>
      )}
    </div>
  );
}
