// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import { redirect } from "next/navigation";
import { api, type NotificationRow, type NotificationTemplate } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { ActionForm } from "@/components/forms/action-form";
import { Badge, Card, Input, Label, Notice, Select } from "@/components/ui";
import { createTemplateAction, templateAction } from "../workflow-actions";
import { When } from "@/components/when";

export const metadata = { title: "Messages · XploVoice" };

type Channel = { channel: string; status: string; note: string | null };
const TPL_TONE = { draft: "amber", approved: "green", retired: "slate" } as const;

export default async function NotificationsPage() {
  const me = await getMe();
  if (!can(me, "support:read")) redirect("/app");
  const [channels, templates, log] = await Promise.all([
    api<Channel[]>("/v1/notification-channels"), api<NotificationTemplate[]>("/v1/notification-templates"),
    api<NotificationRow[]>("/v1/notifications"),
  ]);
  const manage = can(me, "notifications:manage");
  const waiting = channels.filter((c) => c.status !== "configured");
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Messages</h1>
        <p className="text-sm text-slate-600">SMS and email that agents may send, for example a booking confirmation. An agent can only send a template you approved, and only to the contact on the booking, lead or ticket it is about.</p>
      </div>
      {waiting.length > 0 && <Notice>{waiting.map((c) => c.note).join(" ")} Nothing is reported as sent until a provider is set up (awaiting configuration).</Notice>}

      <Card>
        <h2 className="mb-3 font-medium">Templates</h2>
        <div className="space-y-3">
          {templates.length === 0 && <p className="text-sm text-slate-600">No templates yet.</p>}
          {templates.map((t) => (
            <details key={t.id} className="rounded-md border border-slate-200 p-3">
              <summary className="cursor-pointer text-sm"><span className="font-medium">{t.name}</span> <span className="font-mono text-xs text-slate-500">{t.key}</span> · {t.channel} <Badge tone={TPL_TONE[t.status]}>{t.status}</Badge></summary>
              <p className="mt-2 whitespace-pre-wrap rounded bg-slate-50 p-2 text-sm">{t.body}</p>
              {manage && <div className="mt-3 flex flex-wrap items-start gap-3">
                {t.status !== "approved" && <ActionForm action={templateAction} submit="Approve" className=""><input type="hidden" name="id" value={t.id} /><input type="hidden" name="status" value="approved" /></ActionForm>}
                {t.status !== "retired" && <ActionForm action={templateAction} submit="Retire" variant="ghost" className=""><input type="hidden" name="id" value={t.id} /><input type="hidden" name="status" value="retired" /></ActionForm>}
                <ActionForm action={templateAction} submit="Save text (goes back to draft)" variant="secondary" className="w-full space-y-2">
                  <input type="hidden" name="id" value={t.id} />
                  <textarea aria-label="Message text" name="body" defaultValue={t.body} rows={3} maxLength={1000} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
                </ActionForm>
              </div>}
            </details>
          ))}
        </div>
        {manage && <div className="mt-6 border-t border-slate-200 pt-4">
          <h3 className="mb-2 text-sm font-medium">New template</h3>
          <ActionForm action={createTemplateAction} submit="Save draft">
            <div className="grid gap-3 sm:grid-cols-3">
              <div><Label htmlFor="key">Key</Label><Input id="key" name="key" required pattern="[a-z_]{2,40}" placeholder="booking_confirmation" /></div>
              <div><Label htmlFor="name">Name</Label><Input id="name" name="name" required maxLength={120} /></div>
              <div><Label htmlFor="channel">Channel</Label><Select id="channel" name="channel"><option value="sms">SMS</option><option value="email">Email</option></Select></div>
            </div>
            <div><Label htmlFor="subject">Email subject (email only)</Label><Input id="subject" name="subject" maxLength={200} /></div>
            <div><Label htmlFor="body">Text</Label><textarea id="body" name="body" required rows={3} maxLength={1000} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              defaultValue="Hi {customer_name}, your appointment with {business_name} is confirmed for {date_time}. Reference {reference}." /></div>
            <p className="text-xs text-slate-500">Placeholders: {"{customer_name}"}, {"{reference}"}, {"{date_time}"}, {"{business_name}"}.</p>
          </ActionForm>
        </div>}
      </Card>

      <Card className="p-0">
        <h2 className="px-6 pt-5 font-medium">Message log</h2>
        {log.length === 0 ? <p className="p-6 text-sm text-slate-600">No messages yet.</p> : (
          <ul className="mt-2 divide-y divide-slate-100 text-sm">
            {log.map((n) => (
              <li key={n.id} className="px-6 py-3">
                <p className="text-xs text-slate-500"><When iso={n.created_at} /> · {n.channel} to {n.recipient} · <Badge tone={n.status === "held" ? "amber" : n.status === "failed" ? "red" : "slate"}>{n.status}</Badge></p>
                <p>{n.body}</p>
                {n.status_reason && <p className="text-xs text-amber-800">{n.status_reason}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
