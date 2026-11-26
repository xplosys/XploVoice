// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type ConsentRecord, type SuppressionEntry } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { label } from "@/lib/tones";
import { ActionForm } from "@/components/forms/action-form";
import { Badge, Card, Input, Label, Select } from "@/components/ui";
import { When } from "@/components/when";
import { consentAction, revokeConsentAction, suppressAction, unsuppressAction } from "../telephony-actions";

export const metadata = { title: "Do not call · XploVoice" };

const CONSENT_TONE = { granted: "green", declined: "amber", revoked: "red" } as const;

export default async function DoNotCallPage({ searchParams }: { searchParams: Promise<{ phone?: string; removed?: string }> }) {
  const me = await getMe();
  if (!can(me, "consent:read")) redirect("/app");
  const { phone = "", removed } = await searchParams;
  const q = new URLSearchParams();
  if (phone) q.set("phone", phone);
  const manage = can(me, "consent:manage");
  const approve = can(me, "campaigns:approve");
  const [entries, consent] = await Promise.all([
    api<SuppressionEntry[]>(`/v1/suppression?${q}${removed ? "&include_removed=true" : ""}`).catch(() => [] as SuppressionEntry[]),
    api<ConsentRecord[]>(`/v1/consent?${q}&limit=200`).catch(() => [] as ConsentRecord[]),
  ]);
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Do not call and consent</h1>
        <p className="text-sm text-slate-600">A campaign calls a person only with recorded consent, and never while their number is on this list. When someone says &quot;stop calling me&quot; on a call, they are added here and their consent is revoked at once, on every campaign. Records are never deleted.</p>
      </div>
      <form className="flex flex-wrap items-end gap-2">
        <div><Label htmlFor="fphone">Find a number</Label><Input id="fphone" name="phone" defaultValue={phone} placeholder="+91 98123 45671" /></div>
        <label className="flex items-center gap-2 pb-2 text-sm"><input type="checkbox" name="removed" value="1" defaultChecked={!!removed} /> Include removed</label>
        <button className="rounded-md border border-slate-300 px-3 py-2 text-sm" type="submit">Search</button>
        {phone && <Link className="pb-2 text-sm underline" href="/app/do-not-call">Clear</Link>}
      </form>

      <Card className="p-0">
        <h2 className="px-6 pt-5 font-medium">Do-not-call list</h2>
        {entries.length === 0 ? <p className="px-6 pb-6 pt-2 text-sm text-slate-600">No numbers.</p> : (
          <ul className="mt-2 divide-y divide-slate-100 text-sm">
            {entries.map((e) => (
              <li key={e.id} className="space-y-2 px-6 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div><span className="font-mono">{e.phone}</span> <Badge tone={e.removed_at ? "slate" : "red"}>{e.removed_at ? "removed" : label(e.reason)}</Badge>
                    <p className="text-xs text-slate-500">from {e.source} · <When iso={e.created_at} />{e.call_id && <> · <Link className="underline" href={`/app/calls/${e.call_id}`}>on this call</Link></>}{e.note && ` · ${e.note}`}</p>
                    {e.removed_at && <p className="text-xs text-slate-500">Removed <When iso={e.removed_at} />: {e.removed_reason}</p>}</div>
                  {approve && !e.removed_at && (
                    <details><summary className="cursor-pointer text-xs text-brand-700 underline">Take off the list</summary>
                      <ActionForm action={unsuppressAction} submit="Take off the list" variant="secondary" className="mt-2 space-y-2">
                        <input type="hidden" name="id" value={e.id} />
                        <Input name="reason" required maxLength={200} placeholder={e.reason === "opt_out" ? "Why they may be called again (they asked not to be)" : "Reason"} />
                      </ActionForm></details>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        {manage && (
          <div className="border-t border-slate-200 px-6 py-5">
            <ActionForm action={suppressAction} submit="Add to the list">
              <div className="grid gap-3 sm:grid-cols-3">
                <div><Label htmlFor="sphone">Number</Label><Input id="sphone" name="phone" required maxLength={30} /></div>
                <div><Label htmlFor="sreason">Reason</Label><Select id="sreason" name="reason" defaultValue="manual">
                  <option value="manual">Manual</option><option value="opt_out">Asked not to be called</option>
                  <option value="complaint">Complaint</option><option value="do_not_call_registry">National do-not-call registry</option></Select></div>
                <div><Label htmlFor="snote">Note</Label><Input id="snote" name="note" maxLength={500} /></div>
              </div>
            </ActionForm>
          </div>
        )}
      </Card>

      <Card className="p-0">
        <h2 className="px-6 pt-5 font-medium">Consent records</h2>
        {consent.length === 0 ? <p className="px-6 pb-6 pt-2 text-sm text-slate-600">No records.</p> : (
          <ul className="mt-2 divide-y divide-slate-100 text-sm">
            {consent.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 px-6 py-2">
                <div><span className="font-mono">{r.phone}</span> · {label(r.purpose)} <Badge tone={CONSENT_TONE[r.status as keyof typeof CONSENT_TONE] ?? "slate"}>{r.status}</Badge>
                  <p className="text-xs text-slate-500">{label(r.basis)} · from {r.source} · <When iso={r.captured_at} />{r.evidence && ` · ${r.evidence}`}{r.revoked_at && <> · revoked <When iso={r.revoked_at} />: {r.revoked_reason}</>}{r.call_id && <> · <Link className="underline" href={`/app/calls/${r.call_id}`}>call</Link></>}</p></div>
              </li>
            ))}
          </ul>
        )}
        {manage && (
          <div className="grid gap-6 border-t border-slate-200 px-6 py-5 lg:grid-cols-2">
            <ActionForm action={consentAction} submit="Record consent">
              <h3 className="text-sm font-medium">Record consent</h3>
              <div className="grid gap-3 sm:grid-cols-2">
                <div><Label htmlFor="cphone">Number</Label><Input id="cphone" name="phone" required maxLength={30} /></div>
                <div><Label htmlFor="cpurpose">For</Label><Select id="cpurpose" name="purpose"><option value="outbound_calls">Outbound calls</option><option value="recording">Call recording</option></Select></div>
                <div><Label htmlFor="cstatus">Answer</Label><Select id="cstatus" name="status"><option value="granted">Granted</option><option value="declined">Declined</option></Select></div>
                <div><Label htmlFor="cbasis">How</Label><Select id="cbasis" name="basis">
                  <option value="express_written">Written</option><option value="express_verbal">Verbal</option>
                  <option value="existing_relationship">Existing relationship</option><option value="other">Other</option></Select></div>
              </div>
              <div><Label htmlFor="cev">Evidence</Label><Input id="cev" name="evidence" maxLength={1000} placeholder="Where the proof is kept" /></div>
            </ActionForm>
            <ActionForm action={revokeConsentAction} submit="Revoke consent" variant="secondary">
              <h3 className="text-sm font-medium">Revoke consent</h3>
              <div className="grid gap-3 sm:grid-cols-2">
                <div><Label htmlFor="rphone">Number</Label><Input id="rphone" name="phone" required maxLength={30} /></div>
                <div><Label htmlFor="rpurpose">For</Label><Select id="rpurpose" name="purpose"><option value="outbound_calls">Outbound calls</option><option value="recording">Call recording</option></Select></div>
              </div>
              <div><Label htmlFor="rreason">Reason</Label><Input id="rreason" name="reason" required maxLength={200} /></div>
            </ActionForm>
          </div>
        )}
      </Card>
    </div>
  );
}
