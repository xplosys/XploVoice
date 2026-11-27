// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import { redirect } from "next/navigation";
import { api, type ComplianceReport, type Evidence } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { ActionForm } from "@/components/forms/action-form";
import { PrintButton } from "@/components/print-button";
import { Badge, Card, Input, Label, Select } from "@/components/ui";
import { When } from "@/components/when";
import { addEvidenceAction, addRiskAction, revokeEvidenceAction, riskStatusAction } from "../../healthcare-actions";
import { HealthcareTabs } from "../tabs";

export const metadata = { title: "Compliance evidence · XploVoice" };

const label = (s: string) => s.replaceAll("_", " ");
const scoreTone = (n: number) => (n >= 15 ? "red" : n >= 8 ? "amber" : "slate");

export default async function CompliancePage() {
  const me = await getMe();
  if (!can(me, "healthcare:read")) redirect("/app");
  const manage = can(me, "evidence:manage");
  const [rep, evidence] = await Promise.all([
    api<ComplianceReport>("/v1/compliance/report"),
    api<Evidence[]>("/v1/compliance/evidence"),
  ]);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Compliance evidence</h1>
          <p className="text-sm text-slate-600">{rep.organisation} · Healthcare Mode {rep.mode} · generated <When iso={rep.generated_at} /></p>
        </div>
        <PrintButton />
      </div>
      <HealthcareTabs me={me} current="/app/healthcare/compliance" />

      <Card>
        <h2 className="mb-3 text-lg font-medium">Summary</h2>
        <dl className="grid gap-3 text-sm sm:grid-cols-3">
          <div><dt className="text-slate-500">Activation gate</dt><dd className="text-lg font-semibold">{rep.gate.filter((c) => c.ok).length} of {rep.gate.length}</dd></div>
          <div><dt className="text-slate-500">PHI looked at, last 30 days</dt><dd className="text-lg font-semibold">{rep.phi_accesses_30_days} <span className="text-sm font-normal text-slate-500">({rep.phi_denials_30_days} refused)</span></dd></div>
          <div><dt className="text-slate-500">Open incidents</dt><dd className="text-lg font-semibold">{rep.open_incidents}</dd></div>
          <div><dt className="text-slate-500">Rights requests open</dt><dd className="text-lg font-semibold">{rep.rights_requests_open} <span className="text-sm font-normal text-slate-500">({rep.rights_requests_overdue} overdue)</span></dd></div>
          <div><dt className="text-slate-500">Call content kept</dt><dd className="text-lg font-semibold">{rep.retention.call_content ? `${rep.retention.call_content} days` : "not set"}</dd></div>
          <div><dt className="text-slate-500">Open risks</dt><dd className="text-lg font-semibold">{rep.open_risks.length}</dd></div>
        </dl>
        <p className="mt-4 text-xs text-slate-500">{rep.statement}</p>
      </Card>

      <Card className="space-y-3">
        <h2 className="text-lg font-medium">Evidence</h2>
        <p className="text-sm text-slate-600">Where each document or result is kept, not the document itself. Xplosys records your BAA and the platform&apos;s security control tests; you record the rest.</p>
        <table className="w-full text-left text-sm">
          <thead className="text-slate-500"><tr><th className="py-1">Evidence</th><th>Kind</th><th>Valid</th><th>Recorded by</th><th className="print:hidden" /></tr></thead>
          <tbody>{evidence.map((e) => (
            <tr key={e.id} className="border-t border-slate-100 align-top">
              <td className="py-2"><p className="font-medium">{e.title} {e.status === "revoked" && <Badge tone="red">revoked</Badge>}</p>
                {e.reference && <p className="text-xs text-slate-500">{e.reference}</p>}
                {e.kind === "control_test" && Array.isArray(e.details.results) && (
                  <ul className="mt-1 text-xs">{(e.details.results as { key: string; name: string; passed: boolean; detail: string }[]).map((r) => (
                    <li key={r.key}><span className={r.passed ? "text-emerald-700" : "text-red-700"}>{r.passed ? "✓" : "✗"}</span> {r.name}: <span className="text-slate-500">{r.detail}</span></li>))}</ul>)}</td>
              <td className="py-2 capitalize">{label(e.kind)}</td>
              <td className="py-2">{e.valid_from}{e.valid_until ? ` to ${e.valid_until}` : ""}</td>
              <td className="py-2">{e.recorded_kind === "tenant" ? "You" : "Xplosys"}</td>
              <td className="py-2 print:hidden">{manage && e.recorded_kind === "tenant" && e.status === "valid" && (
                <ActionForm action={revokeEvidenceAction} submit="Revoke" variant="ghost" className="flex items-center gap-1">
                  <input type="hidden" name="id" value={e.id} /><Input name="reason" required minLength={5} placeholder="Why" className="w-32" />
                </ActionForm>)}</td>
            </tr>
          ))}</tbody>
        </table>
        {manage && (
          <details className="print:hidden">
            <summary className="cursor-pointer text-sm text-brand-700 underline">Record evidence</summary>
            <ActionForm action={addEvidenceAction} submit="Record" className="mt-3 space-y-3">
              <div className="grid gap-3 sm:grid-cols-3">
                <div><Label htmlFor="e-kind">Kind</Label><Select id="e-kind" name="kind" defaultValue="risk_assessment">
                  {["risk_assessment", "training", "policy_document", "penetration_test", "other"].map((k) => <option key={k} value={k}>{label(k)}</option>)}</Select></div>
                <div><Label htmlFor="e-title">Title</Label><Input id="e-title" name="title" required minLength={3} maxLength={200} /></div>
                <div><Label htmlFor="e-until">Valid until (optional)</Label><Input id="e-until" name="valid_until" type="date" /></div>
              </div>
              <div><Label htmlFor="e-ref">Where it is kept</Label><Input id="e-ref" name="reference" maxLength={300} /></div>
            </ActionForm>
          </details>
        )}
      </Card>

      <Card className="space-y-3">
        <h2 className="text-lg font-medium">Risk register</h2>
        <table className="w-full text-left text-sm">
          <thead className="text-slate-500"><tr><th className="py-1">Risk</th><th>Score</th><th>Status</th><th>Review by</th></tr></thead>
          <tbody>{rep.open_risks.map((r) => (
            <tr key={r.id} className="border-t border-slate-100 align-top">
              <td className="py-2"><p className="font-medium">{r.title}</p>{r.mitigation && <p className="text-xs text-slate-500">{r.mitigation}</p>}</td>
              <td className="py-2"><Badge tone={scoreTone(r.score)}>{r.score}</Badge> <span className="text-xs text-slate-500">{r.likelihood}×{r.impact}</span></td>
              <td className="py-2">{manage ? (
                <ActionForm action={riskStatusAction} submit="Save" variant="ghost" className="flex items-center gap-1">
                  <input type="hidden" name="id" value={r.id} />
                  <Select name="status" defaultValue={r.status} aria-label={`Status of ${r.title}`}>{["open", "mitigating", "accepted", "closed"].map((s) => <option key={s}>{s}</option>)}</Select>
                </ActionForm>) : r.status}</td>
              <td className="py-2">{r.review_by ?? "—"}</td>
            </tr>
          ))}{rep.open_risks.length === 0 && <tr><td colSpan={4} className="py-3 text-slate-500">No open risks.</td></tr>}</tbody>
        </table>
        {manage && (
          <details className="print:hidden">
            <summary className="cursor-pointer text-sm text-brand-700 underline">Add a risk</summary>
            <ActionForm action={addRiskAction} submit="Add" className="mt-3 space-y-3">
              <div><Label htmlFor="k-title">Risk</Label><Input id="k-title" name="title" required minLength={3} maxLength={200} /></div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div><Label htmlFor="k-l">Likelihood (1 to 5)</Label><Input id="k-l" name="likelihood" type="number" min={1} max={5} defaultValue={3} required /></div>
                <div><Label htmlFor="k-i">Impact (1 to 5)</Label><Input id="k-i" name="impact" type="number" min={1} max={5} defaultValue={3} required /></div>
                <div><Label htmlFor="k-r">Review by</Label><Input id="k-r" name="review_by" type="date" /></div>
              </div>
              <div><Label htmlFor="k-m">Mitigation</Label><Input id="k-m" name="mitigation" maxLength={2000} /></div>
            </ActionForm>
          </details>
        )}
      </Card>
    </div>
  );
}
