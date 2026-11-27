// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type Incident } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { ActionForm } from "@/components/forms/action-form";
import { Badge, Card, Input, Label, Select } from "@/components/ui";
import { When } from "@/components/when";
import { reportIncidentAction } from "../../healthcare-actions";
import { HealthcareTabs } from "../tabs";
import { SEVERITY_TONE, STATUS_TONE, tone } from "./tones";

export const metadata = { title: "Incidents · XploVoice" };

const label = (s: string) => s.replaceAll("_", " ");

export default async function IncidentsPage() {
  const me = await getMe();
  if (!can(me, "incidents:report")) redirect("/app");
  const manage = can(me, "incidents:manage");
  const rows = manage ? await api<Incident[]>("/v1/incidents") : [];
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Security incidents</h1>
        <p className="text-sm text-slate-600">Report anything that may have exposed health information: a message sent to the wrong person, a lost device, a vendor&apos;s incident. Describe what happened, not whose information it was: numbers, dates of birth and record numbers are removed when saved.</p>
      </div>
      {can(me, "healthcare:read") && <HealthcareTabs me={me} current="/app/healthcare/incidents" />}
      <Card>
        <h2 className="mb-3 text-lg font-medium">Report an incident</h2>
        <ActionForm action={reportIncidentAction} submit="Report">
          <div><Label htmlFor="i-title">What happened, in a line</Label><Input id="i-title" name="title" required minLength={3} maxLength={200} /></div>
          <div><Label htmlFor="i-sum">Details (optional)</Label><textarea id="i-sum" name="summary" maxLength={4000} rows={3} className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm" /></div>
          <div className="grid gap-3 sm:grid-cols-4">
            <div><Label htmlFor="i-cat">Kind</Label><Select id="i-cat" name="category" defaultValue="other">
              {["unauthorized_access", "misdirected_communication", "lost_device", "vendor_incident", "system_vulnerability", "other"].map((c) => <option key={c} value={c}>{label(c)}</option>)}
            </Select></div>
            <div><Label htmlFor="i-sev">Severity</Label><Select id="i-sev" name="severity" defaultValue="medium">
              {["low", "medium", "high", "critical"].map((c) => <option key={c} value={c}>{c}</option>)}</Select></div>
            <div><Label htmlFor="i-n">People affected (if known)</Label><Input id="i-n" name="affected_individuals" type="number" min={0} defaultValue={0} /></div>
            <div><Label htmlFor="i-at">Discovered</Label><Input id="i-at" name="discovered_at" type="datetime-local" /></div>
          </div>
        </ActionForm>
      </Card>
      {manage && (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500"><tr><th className="px-4 py-2">Incident</th><th className="px-4 py-2">Severity</th>
              <th className="px-4 py-2">Status</th><th className="px-4 py-2">Discovered</th><th className="px-4 py-2">Next notice due</th></tr></thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.id} className="border-t border-slate-100">
                  <td className="px-4 py-2"><Link className="font-medium underline" href={`/app/healthcare/incidents/${i.id}`}>{i.title}</Link><div className="text-xs text-slate-500">{label(i.category)}{i.determination && <> · {label(i.determination)}</>}</div></td>
                  <td className="px-4 py-2"><Badge tone={tone(SEVERITY_TONE, i.severity)}>{i.severity}</Badge></td>
                  <td className="px-4 py-2"><Badge tone={tone(STATUS_TONE, i.status)}>{i.status}</Badge></td>
                  <td className="px-4 py-2"><When iso={i.discovered_at} /></td>
                  <td className="px-4 py-2">{i.next_due_at ? <When iso={i.next_due_at} /> : "—"}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-500">No incidents reported.</td></tr>}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
