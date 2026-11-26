// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { api, ApiError, type Agent, type Campaign, type CampaignContact, type PhoneNumber, type PolicyDecision } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { CAMPAIGN_TONE, CONTACT_TONE, DECISION_TONE, label } from "@/lib/tones";
import { ActionForm } from "@/components/forms/action-form";
import { CampaignFields } from "@/components/forms/campaign-fields";
import { Badge, Card, Input, Label, Select } from "@/components/ui";
import { When } from "@/components/when";
import { campaignStepAction, importContactsAction, removeContactAction, updateCampaignAction } from "../../telephony-actions";

export const metadata = { title: "Campaign · XploVoice" };

const BASES = [["express_written", "Written consent (form, signed, online opt-in)"], ["express_verbal", "Verbal consent"],
  ["existing_relationship", "Existing customer relationship"], ["other", "Other (describe below)"]];

function Step({ id, step, text, variant = "primary" }: { id: string; step: string; text: string; variant?: "primary" | "secondary" | "danger" }) {
  return (
    <ActionForm action={campaignStepAction} submit={text} variant={variant} className="">
      <input type="hidden" name="id" value={id} /><input type="hidden" name="step" value={step} />
    </ActionForm>
  );
}

export default async function CampaignPage({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<{ status?: string }>;
}) {
  const me = await getMe();
  if (!can(me, "campaigns:read")) redirect("/app");
  const { id } = await params;
  const { status } = await searchParams;
  const enc = encodeURIComponent;
  const c = await api<Campaign>(`/v1/campaigns/${enc(id)}`).catch((e) => {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) notFound();
    throw e;
  });
  const manage = can(me, "campaigns:manage");
  const approve = can(me, "campaigns:approve");
  const [contacts, decisions, agents, numbers] = await Promise.all([
    api<CampaignContact[]>(`/v1/campaigns/${enc(id)}/contacts${status ? `?status=${enc(status)}` : ""}`),
    api<PolicyDecision[]>(`/v1/campaigns/${enc(id)}/decisions?limit=50`),
    manage ? api<Agent[]>("/v1/agents").catch(() => [] as Agent[]) : Promise.resolve([] as Agent[]),
    manage && can(me, "telephony:read") ? api<PhoneNumber[]>("/v1/phone-numbers").catch(() => [] as PhoneNumber[]) : Promise.resolve([] as PhoneNumber[]),
  ]);
  const editable = ["draft", "approved", "paused"].includes(c.status);
  const total = Object.values(c.counts).reduce((a, b) => a + b, 0);
  return (
    <div className="space-y-6">
      <div>
        <Link href="/app/campaigns" className="text-sm text-brand-700 underline">All campaigns</Link>
        <h1 className="mt-1 text-2xl font-semibold">{c.name}</h1>
        <p className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <Badge tone={CAMPAIGN_TONE[c.status]}>{c.status}</Badge>
          {c.agent_name} · from <span className="font-mono">{c.from_number}</span> · {c.window_start.slice(0, 5)}–{c.window_end.slice(0, 5)} local time, {c.days.join(", ")}
          {c.approved_at && <> · approved <When iso={c.approved_at} /></>}
        </p>
      </div>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-slate-600">{{
            draft: "Draft: someone with approve rights must approve it before it can call anyone. Any later change needs approval again.",
            approved: "Approved and ready to start.", running: "Calling now, within each person's calling window.",
            paused: "Paused: no new calls. Calls in progress finished normally.", completed: "Finished: everyone was reached, used all attempts, or can't be called.",
            cancelled: "Cancelled.",
          }[c.status]}</p>
          <div className="flex flex-wrap gap-2">
            {approve && c.status === "draft" && <Step id={c.id} step="approve" text="Approve" />}
            {manage && ["approved", "paused"].includes(c.status) && <Step id={c.id} step="start" text={c.status === "paused" ? "Resume" : "Start calling"} />}
            {manage && c.status === "running" && <Step id={c.id} step="pause" text="Pause" variant="secondary" />}
            {manage && !["completed", "cancelled"].includes(c.status) && <Step id={c.id} step="cancel" text="Cancel campaign" variant="danger" />}
          </div>
        </div>
        <ul className="mt-4 flex flex-wrap gap-2 text-xs">
          <li><Link href={`/app/campaigns/${c.id}`} className={`rounded-full border px-3 py-1 ${!status ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-300"}`}>all {total}</Link></li>
          {Object.entries(c.counts).map(([k, v]) => (
            <li key={k}><Link href={`/app/campaigns/${c.id}?status=${k}`} className={`rounded-full border px-3 py-1 ${status === k ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-300"}`}>{label(k)} {v}</Link></li>
          ))}
        </ul>
      </Card>

      <Card className="overflow-x-auto p-0">
        <h2 className="px-6 pt-5 font-medium">Contacts</h2>
        {contacts.length === 0 ? <p className="px-6 pb-6 pt-2 text-sm text-slate-600">No contacts{status ? ` with status ${label(status)}` : ""}.</p> : (
          <table className="mt-3 w-full text-left text-sm">
            <thead className="border-y border-slate-200 text-slate-500"><tr>
              <th className="px-6 py-2 font-medium">Phone</th><th className="px-4 py-2 font-medium">Name</th><th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Attempts</th><th className="px-4 py-2 font-medium">Next try</th><th className="px-4 py-2" /></tr></thead>
            <tbody>
              {contacts.map((k) => (
                <tr key={k.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-6 py-2 font-mono">{k.phone}</td>
                  <td className="px-4 py-2">{k.name || "–"}{k.timezone && <span className="block text-xs text-slate-500">{k.timezone}</span>}</td>
                  <td className="px-4 py-2"><Badge tone={CONTACT_TONE[k.status] ?? "slate"}>{label(k.status)}</Badge>
                    {(k.block_reason || k.last_outcome) && <span className="block text-xs text-slate-500">{label(k.block_reason ?? k.last_outcome ?? "")}</span>}</td>
                  <td className="px-4 py-2">{k.attempts}/{c.max_attempts}{k.last_call_id && <> · <Link className="underline" href={`/app/calls/${k.last_call_id}`}>last call</Link></>}</td>
                  <td className="px-4 py-2">{["pending", "retry"].includes(k.status) ? <When iso={k.next_attempt_at} /> : "–"}</td>
                  <td className="px-4 py-2 text-right">{manage && ["pending", "retry", "blocked"].includes(k.status) && (
                    <ActionForm action={removeContactAction} submit="Remove" variant="ghost" className="">
                      <input type="hidden" name="id" value={c.id} /><input type="hidden" name="contact" value={k.id} />
                    </ActionForm>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {manage && ["draft", "paused"].includes(c.status) && (
        <Card>
          <h2 className="mb-1 font-medium">Add contacts</h2>
          <p className="mb-3 text-sm text-slate-600">One per line: phone number, then optionally a name and a time zone, separated by commas. Adding contacts sends the campaign back for approval.</p>
          <ActionForm action={importContactsAction} submit="Add contacts">
            <input type="hidden" name="id" value={c.id} />
            <textarea name="contacts" rows={5} required className="w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm"
              placeholder={"+91 98123 45671, Asha\n+1 415 555 2671, Sam, America/Los_Angeles"} />
            {can(me, "consent:manage") ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <div><Label htmlFor="basis">Consent these people gave you</Label>
                  <Select id="basis" name="consent_basis" defaultValue=""><option value="">Already recorded (don&apos;t record consent now)</option>
                    {BASES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</Select></div>
                <div><Label htmlFor="ev">Where it is kept (evidence)</Label><Input id="ev" name="consent_evidence" maxLength={1000} placeholder="Sign-up form, 2026 patient intake" /></div>
              </div>
            ) : <p className="text-xs text-slate-500">People without recorded consent are not called. Ask someone with consent rights to record it.</p>}
          </ActionForm>
        </Card>
      )}

      <Card className="overflow-x-auto p-0">
        <h2 className="px-6 pt-5 font-medium">Policy decisions</h2>
        <p className="px-6 text-xs text-slate-500">Every check made before a call, newest first. Blocked numbers never reach the carrier.</p>
        {decisions.length === 0 ? <p className="px-6 pb-6 pt-2 text-sm text-slate-600">None yet.</p> : (
          <ul className="mt-2 divide-y divide-slate-100 text-sm">
            {decisions.map((d) => (
              <li key={d.id} className="px-6 py-2">
                <div className="flex flex-wrap items-center gap-2"><span className="font-mono">{d.phone}</span><Badge tone={DECISION_TONE[d.decision]}>{d.decision}</Badge>
                  {d.reason && <span className="text-xs text-slate-600">{label(d.reason)}</span>}<span className="text-xs text-slate-500"><When iso={d.created_at} time /></span>
                  {d.call_id && <Link className="text-xs underline" href={`/app/calls/${d.call_id}`}>call</Link>}</div>
                <p className="text-xs text-slate-500">{d.checks.map((x) => `${x.ok ? "✓" : "✗"} ${label(x.check)}`).join(" · ")}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {manage && editable && (
        <Card>
          <details>
            <summary className="cursor-pointer font-medium">Edit settings</summary>
            <ActionForm key={c.updated_at} action={updateCampaignAction} submit="Save changes" className="mt-4 space-y-4">
              <input type="hidden" name="id" value={c.id} />
              <CampaignFields agents={agents} numbers={numbers} c={c} />
            </ActionForm>
          </details>
        </Card>
      )}
    </div>
  );
}
