// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { api, ApiError, type GateCheck } from "@/lib/api";
import { getMe } from "@/lib/me";
import { Logo } from "@/components/brand";
import { ActionForm } from "@/components/forms/action-form";
import { ThemePicker } from "@/components/theme-picker";
import { Badge, Card, FormError, Input, Label, Notice, Select } from "@/components/ui";
import { When } from "@/components/when";
import { activateAction, controlTestsAction, customerBaaAction, suspendHcAction, vendorAction } from "./actions";

export const metadata = { title: "Healthcare · Platform admin · XploVoice" };
export const dynamic = "force-dynamic";

type Profile = { tenant_id: string; tenant_name: string; country_code: string; status: string; entity_type: string;
  privacy_contact: string; synthetic_data_only: boolean; requested_at: string; activated_at: string | null;
  activation_reason: string | null; suspended_at: string | null; suspended_reason: string | null; gate: GateCheck[]; gate_passed: boolean };
type Vendor = { id: string; vendor_type: string; vendor_key: string; vendor_name: string; services: string; baa_status: string;
  signed_on: string | null; expires_on: string | null; reference: string; created_at: string };
type Run = { id: string; title: string; created_at: string; details: { passed?: boolean; commit_sha?: string; environment?: string;
  results?: { key: string; name: string; passed: boolean; detail: string }[] } };
type AdminIncident = { id: string; tenant_name: string; title: string; severity: string; status: string; discovered_at: string };

const STATUS_TONE = { requested: "amber", active: "green", suspended: "red", withdrawn: "slate" } as const;
const Reason = () => <Input name="reason" required minLength={5} maxLength={500} placeholder="Reason (audited)" />;

export default async function AdminHealthcare() {
  await getMe();
  let denied: string | null = null;
  let profiles: Profile[] = [], vendors: Vendor[] = [], runs: Run[] = [], incidents: AdminIncident[] = [];
  try {
    [profiles, vendors, runs, incidents] = await Promise.all([
      api<Profile[]>("/admin/v1/healthcare/tenants"), api<Vendor[]>("/admin/v1/healthcare/vendors"),
      api<Run[]>("/admin/v1/healthcare/control-tests"), api<AdminIncident[]>("/admin/v1/healthcare/incidents"),
    ]);
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 403) throw e;
    denied = e.message;
  }
  const latest = runs[0];
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-3"><Logo href="/admin" /><Badge tone="red">Platform admin</Badge></div>
        <nav className="flex items-center gap-4 text-sm"><Link href="/admin" className="text-brand-700 underline">Tenants</Link><Link href="/admin/ai" className="text-brand-700 underline">AI catalog</Link><Link href="/admin/billing" className="text-brand-700 underline">Billing</Link><Link href="/app" className="text-brand-700 underline">Back to workspace</Link><ThemePicker /></nav>
      </header>
      <main className="mx-auto max-w-6xl space-y-6 p-6">
        <div><h1 className="text-2xl font-semibold">Healthcare Mode</h1>
          <p className="text-sm text-slate-600">Organisations that asked for Healthcare Mode, their activation gate, business associate agreements with customers and vendors, and the platform&apos;s security control tests. This console never shows PHI. Every view and change is in the platform audit log.</p></div>
        {denied ? <FormError message={`${denied}. Platform administration needs a platform admin account signed in with two-factor authentication.`} /> : (<>
          <Notice>Activation needs every gate check to pass and an admin other than the person who asked. Synthetic data only outside production. Nothing here is a claim of HIPAA compliance.</Notice>

          <section className="space-y-4">
            <h2 className="text-lg font-medium">Organisations</h2>
            {profiles.length === 0 && <p className="text-sm text-slate-600">No organisation has asked for Healthcare Mode.</p>}
            {profiles.map((p) => (
              <Card key={p.tenant_id} className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div><h3 className="font-medium">{p.tenant_name} <Badge tone={STATUS_TONE[p.status as keyof typeof STATUS_TONE] ?? "slate"}>{p.status}</Badge></h3>
                    <p className="text-sm text-slate-600">{p.entity_type.replaceAll("_", " ")} · {p.country_code} · {p.privacy_contact} · asked <When iso={p.requested_at} />
                      {p.activated_at && <> · active since <When iso={p.activated_at} /></>}{p.suspended_reason && <> · suspended: {p.suspended_reason}</>}</p></div>
                  <Badge tone={p.gate_passed ? "green" : "amber"}>gate {p.gate.filter((c) => c.ok).length}/{p.gate.length}</Badge>
                </div>
                <ul className="grid gap-1 text-sm sm:grid-cols-2">
                  {p.gate.map((c) => <li key={c.key}><span className={c.ok ? "text-emerald-700" : "text-amber-700"}>{c.ok ? "✓" : "○"}</span> {c.label}{!c.ok && <span className="text-slate-500">: {c.detail}</span>}</li>)}
                </ul>
                <div className="grid gap-4 md:grid-cols-2">
                  <details><summary className="cursor-pointer text-sm text-brand-700 underline">Record the customer BAA</summary>
                    <ActionForm action={customerBaaAction} submit="Record BAA" className="mt-2 space-y-2">
                      <input type="hidden" name="tenant_id" value={p.tenant_id} />
                      <Input name="title" required minLength={3} defaultValue={`BAA with ${p.tenant_name}`} aria-label="Title" />
                      <div className="grid grid-cols-2 gap-2"><div><Label htmlFor={`s-${p.tenant_id}`}>Signed</Label><Input id={`s-${p.tenant_id}`} name="signed_on" type="date" required /></div>
                        <div><Label htmlFor={`v-${p.tenant_id}`}>Valid until</Label><Input id={`v-${p.tenant_id}`} name="valid_until" type="date" /></div></div>
                      <Input name="reference" required minLength={3} placeholder="Where the signed copy is kept" aria-label="Reference" /><Reason />
                    </ActionForm></details>
                  <div className="space-y-2">
                    {(p.status === "requested" || p.status === "suspended") && (
                      <ActionForm action={activateAction} submit={p.status === "suspended" ? "Resume Healthcare Mode" : "Activate Healthcare Mode"} className="space-y-2">
                        <input type="hidden" name="tenant_id" value={p.tenant_id} /><Reason />
                      </ActionForm>)}
                    {p.status === "active" && (
                      <ActionForm action={suspendHcAction} submit="Suspend (stop new calls)" variant="danger" className="space-y-2">
                        <input type="hidden" name="tenant_id" value={p.tenant_id} /><Reason />
                      </ActionForm>)}
                  </div>
                </div>
              </Card>
            ))}
          </section>

          <Card className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-medium">Security control tests</h2>
              {latest && <Badge tone={latest.details.passed ? "green" : "red"}>{latest.details.passed ? "passed" : "failed"}{" "}<When iso={latest.created_at} /></Badge>}
            </div>
            <p className="text-sm text-slate-600">Each test reads the live database and configuration. A passing run from the last 30 days is part of every organisation&apos;s activation gate.</p>
            {latest?.details.results && <ul className="text-sm">{latest.details.results.map((r) => <li key={r.key}><span className={r.passed ? "text-emerald-700" : "text-red-700"}>{r.passed ? "✓" : "✗"}</span> {r.name}: <span className="text-slate-500">{r.detail}</span></li>)}</ul>}
            {latest && <p className="text-xs text-slate-500">Commit {latest.details.commit_sha} · {latest.details.environment}</p>}
            <ActionForm action={controlTestsAction} submit="Run control tests" variant="secondary" className="flex max-w-xl items-center gap-2"><Reason /></ActionForm>
          </Card>

          <Card className="space-y-3">
            <h2 className="text-lg font-medium">Vendor BAAs</h2>
            <p className="text-sm text-slate-600">An AI provider receives PHI only with a signed, unexpired BAA here and its PHI approval on in the AI catalog. Recording a termination withdraws the approval at once. Records are never edited: the latest one for a vendor stands.</p>
            <table className="w-full text-left text-sm">
              <thead className="text-slate-500"><tr><th className="py-1">Vendor</th><th>BAA</th><th>Signed</th><th>Expires</th><th>Reference</th><th>Recorded</th></tr></thead>
              <tbody>{vendors.map((v) => (
                <tr key={v.id} className="border-t border-slate-100"><td className="py-1">{v.vendor_name} <span className="font-mono text-xs text-slate-500">{v.vendor_type}:{v.vendor_key}</span></td>
                  <td><Badge tone={v.baa_status === "signed" ? "green" : "red"}>{v.baa_status}</Badge></td><td>{v.signed_on ?? "—"}</td><td>{v.expires_on ?? "—"}</td>
                  <td className="text-slate-600">{v.reference}</td><td><When iso={v.created_at} /></td></tr>))}
                {vendors.length === 0 && <tr><td colSpan={6} className="py-2 text-slate-500">No vendor BAAs recorded.</td></tr>}</tbody>
            </table>
            <details><summary className="cursor-pointer text-sm text-brand-700 underline">Add a vendor record</summary>
              <ActionForm action={vendorAction} submit="Add record" className="mt-3 space-y-2">
                <div className="grid gap-2 sm:grid-cols-4">
                  <Select name="vendor_type" defaultValue="ai_provider" aria-label="Vendor type"><option value="ai_provider">AI provider</option><option value="telephony">Telephony</option><option value="hosting">Hosting</option><option value="other">Other</option></Select>
                  <Input name="vendor_key" required pattern="[a-z0-9_-]{2,60}" placeholder="Key, e.g. openai" aria-label="Vendor key" />
                  <Input name="vendor_name" required minLength={2} placeholder="Name" aria-label="Vendor name" />
                  <Select name="baa_status" defaultValue="signed" aria-label="BAA status"><option value="signed">Signed</option><option value="terminated">Terminated</option></Select>
                </div>
                <div className="grid gap-2 sm:grid-cols-3">
                  <div><Label htmlFor="vd-s">Signed</Label><Input id="vd-s" name="signed_on" type="date" /></div>
                  <div><Label htmlFor="vd-e">Expires</Label><Input id="vd-e" name="expires_on" type="date" /></div>
                  <div><Label htmlFor="vd-sv">Services covered</Label><Input id="vd-sv" name="services" maxLength={300} /></div>
                </div>
                <Input name="reference" required minLength={3} placeholder="Where the signed copy is kept" aria-label="Reference" /><Reason />
              </ActionForm></details>
          </Card>

          <Card className="space-y-2">
            <h2 className="text-lg font-medium">Incidents reported by organisations</h2>
            <ul className="text-sm">{incidents.map((i) => <li key={i.id}>{i.tenant_name}: {i.title} · <Badge tone={i.status === "closed" ? "green" : "amber"}>{i.status}</Badge> {i.severity} · <When iso={i.discovered_at} /></li>)}
              {incidents.length === 0 && <li className="text-slate-500">None.</li>}</ul>
          </Card>
        </>)}
      </main>
    </div>
  );
}
