// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type Ticket } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { PRIORITY_TONE, TICKET_TONE } from "@/lib/tones";
import { ActionForm } from "@/components/forms/action-form";
import { Badge, Card, Input, Label, Select } from "@/components/ui";
import { createTicketAction } from "../workflow-actions";
import { When } from "@/components/when";

export const metadata = { title: "Tickets · XploVoice" };

export default async function TicketsPage({ searchParams }: { searchParams: Promise<{ status?: string }> }) {
  const me = await getMe();
  if (!can(me, "support:read")) redirect("/app");
  const { status = "active" } = await searchParams;
  const tickets = await api<Ticket[]>(`/v1/tickets${status === "all" ? "" : `?status=${encodeURIComponent(status)}`}`);
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Support tickets</h1>
        <p className="text-sm text-slate-600">Problems and requests from callers. An agent opens a ticket when a caller reports a problem, and a high-priority one whenever a caller asks for a person.</p>
      </div>
      <nav className="flex flex-wrap gap-2 text-sm">
        {["active", "open", "pending", "resolved", "closed", "all"].map((s) => (
          <Link key={s} href={`/app/tickets?status=${s}`} className={`rounded-full border px-3 py-1 ${status === s ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-300"}`}>{s}</Link>
        ))}
      </nav>
      <Card className="p-0">
        {tickets.length === 0 ? <p className="p-6 text-sm text-slate-600">No tickets.</p> : (
          <ul className="divide-y divide-slate-100 text-sm">
            {tickets.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center justify-between gap-3 px-6 py-3">
                <div>
                  <Link className="font-medium text-brand-700 underline" href={`/app/tickets/${t.id}`}>{t.subject}</Link>
                  <p className="text-xs text-slate-500"><span className="font-mono">{t.reference}</span> · {t.requester_name || "unknown caller"} · from {t.source} · <When iso={t.created_at} /></p>
                </div>
                <div className="flex gap-2"><Badge tone={PRIORITY_TONE[t.priority]}>{t.priority}</Badge><Badge tone={TICKET_TONE[t.status]}>{t.status}</Badge></div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {can(me, "support:manage") && (
        <Card>
          <h2 className="mb-3 font-medium">Open a ticket</h2>
          <ActionForm action={createTicketAction} submit="Open ticket">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="sm:col-span-2"><Label htmlFor="subject">Subject</Label><Input id="subject" name="subject" required maxLength={200} /></div>
              <div><Label htmlFor="priority">Priority</Label><Select id="priority" name="priority" defaultValue="normal">{["low", "normal", "high", "urgent"].map((p) => <option key={p}>{p}</option>)}</Select></div>
              <div><Label htmlFor="rn">Caller name</Label><Input id="rn" name="requester_name" maxLength={120} /></div>
              <div><Label htmlFor="rp">Caller phone</Label><Input id="rp" name="requester_phone" maxLength={30} /></div>
            </div>
            <div><Label htmlFor="desc">Details</Label><textarea id="desc" name="description" rows={3} maxLength={4000} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" /></div>
          </ActionForm>
        </Card>
      )}
    </div>
  );
}
