// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { api, ApiError, type IncidentDetail } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { ActionForm } from "@/components/forms/action-form";
import { Badge, Card, Input, Label, Notice, Select } from "@/components/ui";
import { When } from "@/components/when";
import { assessIncidentAction, closeIncidentAction, noticeSentAction, updateIncidentAction } from "../../../healthcare-actions";
import { SEVERITY_TONE, STATUS_TONE, tone } from "../tones";

export const metadata = { title: "Incident · XploVoice" };

const label = (s: string) => s.replaceAll("_", " ");
const AUDIENCE: Record<string, string> = {
  individuals: "The people affected", hhs: "HHS (Office for Civil Rights)", media: "Prominent media in the affected state",
  covered_entity: "The covered entity you work for",
};
const FACTORS: [string, string][] = [
  ["nature_and_extent", "1. The nature and extent of the health information involved"],
  ["unauthorized_recipient", "2. Who used it or received it"],
  ["acquired_or_viewed", "3. Whether it was actually acquired or viewed"],
  ["mitigation", "4. How far the risk has been reduced"],
];
const Area = ({ name, id }: { name: string; id: string }) => (
  <textarea id={id} name={name} required minLength={3} maxLength={2000} rows={2} className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm" />
);

export default async function IncidentPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await getMe();
  if (!can(me, "incidents:manage")) redirect("/app/healthcare/incidents");
  const { id } = await params;
  let i: IncidentDetail;
  try {
    i = await api<IncidentDetail>(`/v1/incidents/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  const open = i.status !== "closed";
  const latest = i.assessments[0];
  return (
    <div className="space-y-6">
      <div>
        <Link href="/app/healthcare/incidents" className="text-sm text-brand-700 underline">Incidents</Link>
        <h1 className="text-2xl font-semibold">{i.title}</h1>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <Badge tone={tone(STATUS_TONE, i.status)}>{i.status}</Badge><Badge tone={tone(SEVERITY_TONE, i.severity)}>{i.severity}</Badge>
          <span>{label(i.category)}</span><span>· discovered <When iso={i.discovered_at} /></span>
          <span>· {i.affected_individuals} {i.affected_individuals === 1 ? "person" : "people"} affected</span><span>· PHI involved: {i.phi_involved}</span>
        </p>
        {i.summary && <p className="mt-2 text-sm">{i.summary}</p>}
      </div>
      <Notice>Target dates are for tracking and follow the HIPAA Breach Notification Rule as commonly read (60 days from discovery). XploVoice sends no notices and gives no legal advice: confirm each one with your counsel.</Notice>

      {open && (
        <Card>
          <h2 className="mb-3 text-lg font-medium">Details</h2>
          <ActionForm action={updateIncidentAction} submit="Save" variant="secondary">
            <input type="hidden" name="id" value={i.id} />
            <div className="grid gap-3 sm:grid-cols-3">
              <div><Label htmlFor="u-sev">Severity</Label><Select id="u-sev" name="severity" defaultValue={i.severity}>{["low", "medium", "high", "critical"].map((c) => <option key={c}>{c}</option>)}</Select></div>
              <div><Label htmlFor="u-phi">PHI involved</Label><Select id="u-phi" name="phi_involved" defaultValue={i.phi_involved}>{["unknown", "yes", "no"].map((c) => <option key={c}>{c}</option>)}</Select></div>
              <div><Label htmlFor="u-n">People affected</Label><Input id="u-n" name="affected_individuals" type="number" min={0} defaultValue={i.affected_individuals} /></div>
            </div>
          </ActionForm>
        </Card>
      )}

      <Card className="space-y-4">
        <h2 className="text-lg font-medium">Risk assessment</h2>
        {latest ? (
          <div className="space-y-1 text-sm">
            <p><Badge tone={latest.determination === "breach" ? "red" : "green"}>{latest.determination === "breach" ? "Breach" : "Not a breach"}</Badge> <span className="text-slate-600">probability of compromise {latest.risk === "low" ? "low" : "not low"}{latest.exception !== "none" && <>, exception: {label(latest.exception)}</>} · <When iso={latest.assessed_at} /></span></p>
            {FACTORS.map(([k, l]) => <p key={k}><span className="font-medium">{l}:</span> {(latest as unknown as Record<string, string>)[k]}</p>)}
          </div>
        ) : <p className="text-sm text-slate-600">Not assessed yet.</p>}
        {open && (
          <details open={!latest}>
            <summary className="cursor-pointer text-sm text-brand-700 underline">{latest ? "Assess again" : "Record the assessment"}</summary>
            <ActionForm action={assessIncidentAction} submit="Save assessment" className="mt-3 space-y-3">
              <input type="hidden" name="id" value={i.id} />
              {FACTORS.map(([k, l]) => <div key={k}><Label htmlFor={`a-${k}`}>{l}</Label><Area id={`a-${k}`} name={k} /></div>)}
              <div className="grid gap-3 sm:grid-cols-2">
                <div><Label htmlFor="a-risk">Probability the information was compromised</Label><Select id="a-risk" name="risk" defaultValue="not_low"><option value="not_low">Not low</option><option value="low">Low</option></Select></div>
                <div><Label htmlFor="a-ex">Exception</Label><Select id="a-ex" name="exception" defaultValue="none">
                  <option value="none">None</option><option value="unintentional_workforce_access">Unintentional access by staff, in good faith</option>
                  <option value="inadvertent_internal_disclosure">Inadvertent disclosure between authorised people</option>
                  <option value="unable_to_retain">Recipient could not have kept it</option></Select></div>
              </div>
            </ActionForm>
          </details>
        )}
      </Card>

      {i.notifications.length > 0 && (
        <Card>
          <h2 className="mb-3 text-lg font-medium">Notices required</h2>
          <ul className="divide-y divide-slate-100 text-sm">
            {i.notifications.map((n) => (
              <li key={n.id} className="flex flex-wrap items-center justify-between gap-3 py-2">
                <div><p className="font-medium">{AUDIENCE[n.audience] ?? n.audience}</p>
                  <p className="text-slate-600">Due by <When iso={n.due_at} />{n.sent_at && <> · sent <When iso={n.sent_at} /> by {n.method}</>}</p></div>
                {n.sent_at ? <Badge tone="green">sent</Badge> : open && (
                  <ActionForm action={noticeSentAction} submit="Record as sent" variant="secondary" className="flex items-center gap-2">
                    <input type="hidden" name="id" value={i.id} /><input type="hidden" name="notification_id" value={n.id} />
                    <Input name="method" required minLength={2} maxLength={100} placeholder="How (letter, email, portal)" />
                  </ActionForm>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {open ? (
        <Card>
          <h2 className="mb-3 text-lg font-medium">Close the incident</h2>
          <ActionForm action={closeIncidentAction} submit="Close" variant="secondary">
            <input type="hidden" name="id" value={i.id} />
            <Input name="note" required minLength={5} maxLength={1000} placeholder="What was done" />
          </ActionForm>
        </Card>
      ) : <p className="text-sm text-slate-600">Closed <When iso={i.closed_at!} />: {i.close_note}</p>}
    </div>
  );
}
