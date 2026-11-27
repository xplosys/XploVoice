// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import { redirect } from "next/navigation";
import { api, ApiError, type RetentionOverview } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { ActionForm } from "@/components/forms/action-form";
import { Badge, Card, Input, Label, Notice, Select } from "@/components/ui";
import { When } from "@/components/when";
import {
  completeRequestAction, decideRequestAction, logRequestAction, placeHoldAction, releaseHoldAction, retentionPolicyAction,
  runRetentionAction,
} from "../../healthcare-actions";
import { HealthcareTabs } from "../tabs";

export const metadata = { title: "Retention and rights · XploVoice" };

const KIND: Record<string, string> = {
  access: "Access (a copy of their calls)", amendment: "Amendment (a statement added)", deletion: "Deletion",
  restriction: "Restriction",
};
const REQ_TONE = { received: "amber", approved: "brand", rejected: "slate", completed: "green" } as const;

export default async function RetentionPage() {
  const me = await getMe();
  if (!can(me, "retention:manage")) redirect("/app");
  let r: RetentionOverview | null = null;
  try {
    r = await api<RetentionOverview>("/v1/retention");
  } catch (e) {
    if (!(e instanceof ApiError)) throw e;
  }
  if (!r) redirect("/app/healthcare");
  const days = Object.fromEntries(r.policies.map((p) => [p.resource_type, p.retain_days]));
  const now = Date.now();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Retention and patient rights</h1>
        <p className="text-sm text-slate-600">How long call content is kept, legal holds that stop anything being removed, and requests from patients to see, amend or delete their records.</p>
      </div>
      <HealthcareTabs me={me} current="/app/healthcare/retention" />

      <Card className="space-y-4">
        <h2 className="text-lg font-medium">Retention schedule</h2>
        <p className="text-sm text-slate-600">After this many days from the end of a call, its transcript, event details, tool inputs and the caller&apos;s number are removed. The call itself (time, length, agent) stays for billing and analytics. Your state&apos;s medical-record rules may need longer.</p>
        <div className="grid gap-4 sm:grid-cols-2">
          {([["call_content", "Call content"], ["call_recording", "Recordings (when storage is configured)"]] as const).map(([k, l]) => (
            <ActionForm key={k} action={retentionPolicyAction} submit="Save" variant="secondary" className="space-y-2">
              <input type="hidden" name="resource_type" value={k} />
              <Label htmlFor={`r-${k}`}>{l}, days</Label>
              <Input id={`r-${k}`} name="retain_days" type="number" min={1} max={36500} required defaultValue={days[k]} />
            </ActionForm>
          ))}
        </div>
        <ActionForm action={runRetentionAction} submit="Remove expired content now" variant="secondary" />
        {r.runs.length > 0 && <ul className="text-sm text-slate-600">{r.runs.slice(0, 5).map((x) => <li key={x.id}><When iso={x.ran_at} />: {x.calls_purged} removed, {x.skipped_on_hold} kept under a hold</li>)}</ul>}
      </Card>

      <Card className="space-y-4">
        <h2 className="text-lg font-medium">Legal holds</h2>
        <ul className="divide-y divide-slate-100 text-sm">
          {r.holds.map((h) => (
            <li key={h.id} className="flex flex-wrap items-center justify-between gap-3 py-2">
              <div><p className="font-medium">{h.scope === "all" ? "Everything" : h.scope === "call" ? <>Call <span className="font-mono text-xs">{h.call_id?.slice(0, 8)}</span></> : <>Number {h.phone}</>}{" "}
                {h.released_at ? <Badge>released</Badge> : <Badge tone="red">active</Badge>}</p>
                <p className="text-slate-600">{h.reason} · placed <When iso={h.placed_at} />{h.released_at && <> · released: {h.release_reason}</>}</p></div>
              {!h.released_at && (
                <ActionForm action={releaseHoldAction} submit="Release" variant="secondary" className="flex items-center gap-2">
                  <input type="hidden" name="id" value={h.id} /><Input name="reason" required minLength={5} placeholder="Why it can be released" />
                </ActionForm>
              )}
            </li>
          ))}
          {r.holds.length === 0 && <li className="py-2 text-slate-500">No holds.</li>}
        </ul>
        <details>
          <summary className="cursor-pointer text-sm text-brand-700 underline">Place a hold</summary>
          <ActionForm action={placeHoldAction} submit="Place hold" className="mt-3 space-y-3">
            <div className="grid gap-3 sm:grid-cols-3">
              <div><Label htmlFor="h-scope">Covers</Label><Select id="h-scope" name="scope" defaultValue="phone">
                <option value="phone">One person&apos;s number</option><option value="call">One call</option><option value="all">Everything</option></Select></div>
              <div><Label htmlFor="h-phone">Number (for one person)</Label><Input id="h-phone" name="phone" placeholder="+1 415 555 0123" /></div>
              <div><Label htmlFor="h-call">Call id (for one call)</Label><Input id="h-call" name="call_id" /></div>
            </div>
            <div><Label htmlFor="h-reason">Reason</Label><Input id="h-reason" name="reason" required minLength={5} maxLength={500} /></div>
          </ActionForm>
        </details>
      </Card>

      <Card className="space-y-4">
        <h2 className="text-lg font-medium">Patient rights requests</h2>
        <p className="text-sm text-slate-600">Log a request once you have checked who is asking. Someone else approves or rejects it; then it is completed here. Target dates: 30 days, 60 for an amendment.</p>
        {r.requests.length > 0 && (
          <ul className="divide-y divide-slate-100 text-sm">
            {r.requests.map((q) => (
              <li key={q.id} className="space-y-2 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{KIND[q.kind]}</span><Badge tone={REQ_TONE[q.status as keyof typeof REQ_TONE] ?? "slate"}>{q.status}</Badge>
                  <span className="font-mono text-xs">{q.subject_phone}</span>{q.subject_reference && <span>· {q.subject_reference}</span>}
                  <span className="text-slate-600">· received <When iso={q.received_at} /> · due <When iso={q.due_at} /></span>
                  {["received", "approved"].includes(q.status) && new Date(q.due_at).getTime() < now && <Badge tone="red">overdue</Badge>}
                </div>
                {q.details && <p className="text-slate-600">{q.details}</p>}
                {q.decision_reason && <p className="text-slate-600">Decision: {q.decision_reason}</p>}
                {q.outcome && <p className="text-slate-600">Outcome: {String(q.outcome.calls ?? 0)} call(s){q.outcome.purged !== undefined && <>, {String(q.outcome.purged)} removed</>}{q.outcome.note ? <>, {String(q.outcome.note)}</> : null}</p>}
                {q.status === "received" && (q.logged_by_you ? <p className="text-slate-500">You logged this request, so someone else must decide it.</p> : (
                  <ActionForm action={decideRequestAction} submit="Record decision" variant="secondary" className="flex flex-wrap items-center gap-2">
                    <input type="hidden" name="id" value={q.id} />
                    <Select name="decision" defaultValue="approve" className="max-w-[9rem]" aria-label="Decision"><option value="approve">Approve</option><option value="reject">Reject</option></Select>
                    <Input name="reason" required minLength={5} placeholder="Reason" className="max-w-sm" />
                  </ActionForm>))}
                {q.status === "approved" && (
                  <div className="flex flex-wrap items-center gap-3">
                    {q.kind === "access" && can(me, "phi:read") && <a className="text-brand-700 underline" href={`/app/healthcare/retention/export/${q.id}`}>Download their calls (JSON)</a>}
                    <ActionForm action={completeRequestAction} submit={q.kind === "deletion" ? "Delete their call content" : "Mark completed"} variant={q.kind === "deletion" ? "danger" : "secondary"} className="flex items-center gap-2">
                      <input type="hidden" name="id" value={q.id} />
                      <Input name="note" maxLength={1000} placeholder={q.kind === "amendment" ? "Statement to add to their records" : "Note (optional)"} required={q.kind === "amendment"} />
                    </ActionForm>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {!can(me, "phi:read") && <Notice>Numbers are partly hidden because your role can&apos;t see PHI.</Notice>}
        <details>
          <summary className="cursor-pointer text-sm text-brand-700 underline">Log a request</summary>
          <ActionForm action={logRequestAction} submit="Log request" className="mt-3 space-y-3">
            <div className="grid gap-3 sm:grid-cols-3">
              <div><Label htmlFor="q-kind">Request</Label><Select id="q-kind" name="kind" defaultValue="access">{Object.entries(KIND).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></div>
              <div><Label htmlFor="q-phone">Their phone number</Label><Input id="q-phone" name="subject_phone" required placeholder="+1 415 555 0123" /></div>
              <div><Label htmlFor="q-ref">Your reference (optional)</Label><Input id="q-ref" name="subject_reference" maxLength={100} /></div>
            </div>
            <div><Label htmlFor="q-details">Details (optional)</Label><Input id="q-details" name="details" maxLength={2000} /></div>
          </ActionForm>
        </details>
      </Card>
    </div>
  );
}
