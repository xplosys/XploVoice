// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { api, ApiError, type TicketDetail } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { PRIORITY_TONE, TICKET_TONE } from "@/lib/tones";
import { ActionForm } from "@/components/forms/action-form";
import { Badge, Card, Label, Select } from "@/components/ui";
import { ticketAction, ticketCommentAction } from "../../workflow-actions";
import { When } from "@/components/when";

export const metadata = { title: "Ticket · XploVoice" };

export default async function TicketPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await getMe();
  if (!can(me, "support:read")) redirect("/app");
  const { id } = await params;
  const t = await api<TicketDetail>(`/v1/tickets/${encodeURIComponent(id)}`).catch((e) => {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) notFound();
    throw e;
  });
  const manage = can(me, "support:manage");
  return (
    <div className="space-y-6">
      <div>
        <Link href="/app/tickets" className="text-sm text-brand-700 underline">All tickets</Link>
        <h1 className="mt-1 text-2xl font-semibold">{t.subject}</h1>
        <p className="flex flex-wrap items-center gap-2 text-sm text-slate-600"><span className="font-mono">{t.reference}</span>
          <Badge tone={PRIORITY_TONE[t.priority]}>{t.priority}</Badge><Badge tone={TICKET_TONE[t.status]}>{t.status}</Badge>
          from {t.source} · <When iso={t.created_at} />{t.call_id && <> · <Link className="underline" href={`/app/calls/${t.call_id}`}>call record</Link></>}</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
        <Card>
          <dl className="mb-4 grid gap-3 text-sm sm:grid-cols-3">
            <div><dt className="text-xs text-slate-500">Caller</dt><dd>{t.requester_name || "–"}</dd></div>
            <div><dt className="text-xs text-slate-500">Phone</dt><dd>{t.requester_phone || "–"}</dd></div>
            <div><dt className="text-xs text-slate-500">Email</dt><dd>{t.requester_email || "–"}</dd></div>
          </dl>
          <p className="whitespace-pre-wrap text-sm">{t.description || "No details."}</p>
          <h2 className="mb-2 mt-6 font-medium">Comments</h2>
          <ol className="space-y-2 text-sm">
            {t.comments.length === 0 && <li className="text-slate-600">None yet.</li>}
            {t.comments.map((c, i) => (
              <li key={i} className="rounded-md border border-slate-200 p-2">
                <p className="text-xs text-slate-500"><When iso={c.created_at} />{c.internal && " · internal"}</p>
                <p className="whitespace-pre-wrap">{c.body}</p>
              </li>
            ))}
          </ol>
          {manage && <div className="mt-4 border-t border-slate-200 pt-4">
            <ActionForm action={ticketCommentAction} submit="Add comment">
              <input type="hidden" name="id" value={t.id} />
              <div><Label htmlFor="body">Internal comment</Label><textarea id="body" name="body" required rows={3} maxLength={4000} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" /></div>
            </ActionForm>
          </div>}
        </Card>
        {manage && <Card>
          <h2 className="mb-2 font-medium">Update</h2>
          <ActionForm key={`${t.status}-${t.priority}`} action={ticketAction} submit="Save">
            <input type="hidden" name="id" value={t.id} />
            <div><Label htmlFor="st">Status</Label><Select id="st" name="status" defaultValue={t.status}>{["open", "pending", "resolved", "closed"].map((s) => <option key={s}>{s}</option>)}</Select></div>
            <div><Label htmlFor="pr">Priority</Label><Select id="pr" name="priority" defaultValue={t.priority}>{["low", "normal", "high", "urgent"].map((s) => <option key={s}>{s}</option>)}</Select></div>
          </ActionForm>
        </Card>}
      </div>
    </div>
  );
}
