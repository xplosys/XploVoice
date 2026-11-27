// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { api, ApiError, type AdminPlan } from "@/lib/api";
import { getMe } from "@/lib/me";
import { fmtMoney, fmtPrice } from "@/lib/utils";
import { Copyright, Logo } from "@/components/brand";
import { ActionForm } from "@/components/forms/action-form";
import { ThemePicker } from "@/components/theme-picker";
import { Badge, Card, FormError, Input, Label, Select } from "@/components/ui";
import { When } from "@/components/when";
import {
  addPriceAction, assignPlanAction, closePeriodAction, createPlanAction, creditAction, fxAction, planStatusAction,
  runBillingAction, taxAction,
} from "./actions";

export const metadata = { title: "Billing · Platform admin · XploVoice" };
export const dynamic = "force-dynamic";

type Overview = { currency: string; organisations: number; active_subscriptions: number; monthly_plan_fees: string;
  charges_this_month: string; provider_cost_this_month: string | null; provider_cost_unconverted: string[];
  margin_this_month: string | null; open_invoice_amount: string };
type Sub = { tenant_id: string; tenant_name: string; currency: string; subscription_id: string | null; plan: string | null;
  pending_plan: string | null; status: string | null; current_period_end: string | null; cancel_at_period_end: boolean;
  period_charges: string; open_invoices: number; open_amount: string };
type Fx = { base: string; quote: string; rate: string; source: string; effective_from: string };
type Tax = { country_code: string; label: string; rate_percent: string; source: string; effective_from: string };

const METERS: [string, string][] = [["phone_inbound_minute", "Inbound phone, per minute"], ["phone_outbound_minute", "Outbound phone, per minute"],
  ["llm_input_1k_tokens", "AI input, per 1,000 tokens"], ["llm_output_1k_tokens", "AI output, per 1,000 tokens"],
  ["stt_minute", "Speech-to-text, per minute"], ["tts_1k_characters", "Text-to-speech, per 1,000 characters"]];
const PLAN_TONE = { draft: "slate", active: "green", retired: "red" } as const;
const Reason = () => <Input name="reason" required minLength={5} maxLength={500} placeholder="Reason (audited)" />;

export default async function AdminBilling() {
  await getMe();
  let denied: string | null = null;
  let overview: Overview[] = [], plans: AdminPlan[] = [], subs: Sub[] = [], fx: Fx[] = [], tax: Tax[] = [];
  try {
    [overview, plans, subs, fx, tax] = await Promise.all([
      api<Overview[]>("/admin/v1/billing/overview"), api<AdminPlan[]>("/admin/v1/billing/plans"),
      api<Sub[]>("/admin/v1/billing/subscriptions"), api<Fx[]>("/admin/v1/billing/fx-rates"), api<Tax[]>("/admin/v1/billing/tax-rates"),
    ]);
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 403) throw e;
    denied = e.message;
  }
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-3"><Logo href="/admin" /><Badge tone="red">Platform admin</Badge></div>
        <nav className="flex items-center gap-4 text-sm"><Link href="/admin" className="text-brand-700 underline">Tenants</Link><Link href="/admin/ai" className="text-brand-700 underline">AI catalog</Link><Link href="/app" className="text-brand-700 underline">Back to workspace</Link><ThemePicker /></nav>
      </header>
      <main className="mx-auto max-w-6xl space-y-6 p-6">
        <div><h1 className="text-2xl font-semibold">Billing</h1>
          <p className="text-sm text-slate-600">Plans, prices, tax and FX rates, and every organisation&apos;s subscription. No plans, prices, tax or FX rates are built in: each is entered here with its source, and a price change applies from the moment it is added. Every view and change is in the platform audit log.</p></div>
        {denied ? <FormError message={`${denied}. Platform administration needs a platform admin account signed in with two-factor authentication.`} /> : (<>
          <div className="grid gap-4 md:grid-cols-2">
            {overview.map((o) => (
              <Card key={o.currency} className="space-y-1 text-sm">
                <h2 className="font-medium">{o.currency} organisations ({o.organisations})</h2>
                <p>Active subscriptions: {o.active_subscriptions} · plan fees {fmtMoney(o.monthly_plan_fees, o.currency)} a month</p>
                <p>Charges this month: <span className="font-medium">{fmtMoney(o.charges_this_month, o.currency)}</span></p>
                <p>Provider cost this month: {o.provider_cost_this_month !== null ? fmtMoney(o.provider_cost_this_month, o.currency) : <span className="text-amber-700">needs an FX rate for {o.provider_cost_unconverted.join(", ")}</span>}</p>
                <p>Margin this month: {o.margin_this_month !== null ? fmtMoney(o.margin_this_month, o.currency) : "—"}</p>
                <p>Open invoices: {fmtMoney(o.open_invoice_amount, o.currency)}</p>
              </Card>
            ))}
          </div>
          <Card><ActionForm action={runBillingAction} submit="Run billing now" variant="secondary" className="flex flex-wrap items-end gap-2">
            <div className="min-w-64 flex-1"><Label htmlFor="runr">Rates new use and invoices every period that has ended (it also runs every 5 minutes)</Label><Input id="runr" name="reason" required minLength={5} maxLength={500} placeholder="Reason (audited)" /></div>
          </ActionForm></Card>

          <Card className="overflow-x-auto p-0">
            <h2 className="px-6 pt-5 font-medium">Organisations</h2>
            <table className="mt-2 w-full text-left text-sm"><thead className="border-b border-slate-200 text-slate-500"><tr>
              <th className="px-6 py-2 font-medium">Organisation</th><th className="px-3 py-2 font-medium">Plan</th><th className="px-3 py-2 text-right font-medium">This period</th>
              <th className="px-3 py-2 text-right font-medium">Open invoices</th><th className="px-6 py-2 font-medium">Actions (reason required)</th></tr></thead>
              <tbody>{subs.map((s) => (
                <tr key={s.tenant_id} className="border-b border-slate-100 align-top last:border-0">
                  <td className="px-6 py-3"><div className="font-medium">{s.tenant_name}</div><div className="text-xs text-slate-500">{s.currency}</div></td>
                  <td className="px-3 py-3">{s.plan ? <>{s.plan} <Badge tone={s.status === "past_due" ? "red" : "green"}>{s.status?.replace("_", " ")}</Badge>
                    {s.current_period_end && <div className="text-xs text-slate-500">period ends <When iso={s.current_period_end} /></div>}
                    {s.pending_plan && <div className="text-xs text-slate-500">then {s.pending_plan}</div>}
                    {s.cancel_at_period_end && <div className="text-xs text-red-700">ends with this period</div>}</> : <span className="text-slate-500">No plan (unbilled)</span>}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{fmtMoney(s.period_charges, s.currency)}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{s.open_invoices ? `${s.open_invoices} · ${fmtMoney(s.open_amount, s.currency)}` : "—"}</td>
                  <td className="space-y-2 px-6 py-3">
                    <details><summary className="cursor-pointer text-xs text-brand-700 underline">Assign plan</summary>
                      <ActionForm action={assignPlanAction} submit="Assign" variant="secondary" className="mt-2 space-y-2">
                        <input type="hidden" name="tenant_id" value={s.tenant_id} />
                        <Select name="plan_id" aria-label="Plan">{plans.filter((p) => p.status === "active" && p.currency === s.currency).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select><Reason />
                      </ActionForm></details>
                    {s.subscription_id && <>
                      <details><summary className="cursor-pointer text-xs text-brand-700 underline">Add a credit</summary>
                        <ActionForm action={creditAction} submit="Credit" variant="secondary" className="mt-2 space-y-2">
                          <input type="hidden" name="tenant_id" value={s.tenant_id} />
                          <Input name="amount" type="number" min="0.01" step="0.01" required placeholder={`Amount (${s.currency})`} /><Reason />
                        </ActionForm></details>
                      <details><summary className="cursor-pointer text-xs text-brand-700 underline">Close the period now</summary>
                        <ActionForm action={closePeriodAction} submit="Close and invoice" variant="danger" className="mt-2 space-y-2">
                          <input type="hidden" name="tenant_id" value={s.tenant_id} /><Reason />
                        </ActionForm></details></>}
                  </td>
                </tr>))}</tbody></table>
          </Card>

          <h2 className="pt-2 text-lg font-medium">Plans</h2>
          <div className="grid gap-4 lg:grid-cols-2">
            {plans.map((p) => (
              <Card key={p.id} className="space-y-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-medium">{p.name} <span className="text-slate-500">({p.code})</span></h3>
                  <div className="flex gap-1"><Badge tone={PLAN_TONE[p.status as keyof typeof PLAN_TONE] ?? "slate"}>{p.status}</Badge>{p.is_default && <Badge tone="brand">default for new {p.currency} organisations</Badge>}</div>
                </div>
                <p className="text-slate-600">{p.kind === "payg" ? "Pay as you go" : "Monthly"} · {p.currency} · {p.subscribers} subscribed{p.trial_days ? ` · ${p.trial_days}-day trial` : ""}
                  {Object.entries(p.limits).map(([k, v]) => ` · ${k.replace("max_", "max ").replaceAll("_", " ")} ${v}`)}</p>
                <ul className="space-y-0.5">{p.prices.map((x) => (
                  <li key={x.meter}>{x.label}: {fmtPrice(x.unit_price, p.currency)}{x.meter !== "base_fee" && ` per ${x.unit}`}{Number(x.included_quantity) > 0 && `, ${Number(x.included_quantity)} included`}{x.monthly_cap && `, quota ${Number(x.monthly_cap)}`} <span className="text-xs text-slate-500">since <When iso={x.effective_from} /></span></li>))}</ul>
                {p.status !== "retired" && <>
                  <details><summary className="cursor-pointer text-xs text-brand-700 underline">Change a price</summary>
                    <ActionForm action={addPriceAction} submit="Add price" variant="secondary" className="mt-2 space-y-2">
                      <input type="hidden" name="id" value={p.id} />
                      <Select name="meter" aria-label="Meter">{[["base_fee", "Plan fee, per month"], ...METERS].map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
                      <div className="grid grid-cols-3 gap-2"><Input name="unit_price" required type="number" min="0" step="any" placeholder="Price" aria-label="Price" />
                        <Input name="included_quantity" type="number" min="0" step="any" placeholder="Included" aria-label="Included" />
                        <Input name="monthly_cap" type="number" min="0" step="any" placeholder="Quota" aria-label="Quota" /></div><Reason />
                    </ActionForm></details>
                  <details><summary className="cursor-pointer text-xs text-brand-700 underline">{p.status === "draft" ? "Activate" : "Default or retire"}</summary>
                    <ActionForm action={planStatusAction} submit="Save" variant="secondary" className="mt-2 space-y-2">
                      <input type="hidden" name="id" value={p.id} />
                      <Select name="status" aria-label="Status" defaultValue="active"><option value="active">Active (offered)</option><option value="retired">Retired (no new subscriptions)</option></Select>
                      <label className="flex items-center gap-2"><input type="checkbox" name="is_default" defaultChecked={p.is_default} /> New {p.currency} organisations start on this plan</label><Reason />
                    </ActionForm></details></>}
              </Card>))}
            {plans.length === 0 && <p className="text-sm text-slate-600">No plans yet.</p>}
          </div>

          <Card>
            <h2 className="font-medium">New plan</h2>
            <ActionForm action={createPlanAction} submit="Create plan" className="mt-3 space-y-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <div><Label htmlFor="pcode">Code</Label><Input id="pcode" name="code" required pattern="[a-z0-9][a-z0-9_\-]{1,39}" placeholder="growth-inr" /></div>
                <div><Label htmlFor="pname">Name</Label><Input id="pname" name="name" required maxLength={80} /></div>
                <div><Label htmlFor="pkind">Kind</Label><Select id="pkind" name="kind"><option value="subscription">Monthly subscription</option><option value="payg">Pay as you go</option></Select></div>
                <div><Label htmlFor="pcur">Currency</Label><Select id="pcur" name="currency"><option>INR</option><option>USD</option></Select></div>
                <div><Label htmlFor="pfee">Plan fee a month</Label><Input id="pfee" name="fee" type="number" min="0" step="0.01" /></div>
                <div><Label htmlFor="ptrial">Trial days</Label><Input id="ptrial" name="trial_days" type="number" min="0" max="90" defaultValue={0} /></div>
                <div><Label htmlFor="pma">Max agents</Label><Input id="pma" name="max_agents" type="number" min="1" placeholder="No limit" /></div>
                <div><Label htmlFor="pmc">Max calls at once</Label><Input id="pmc" name="max_concurrent_calls" type="number" min="1" placeholder="Platform limit" /></div>
                <div><Label htmlFor="pmn">Max phone numbers</Label><Input id="pmn" name="max_phone_numbers" type="number" min="0" placeholder="No limit" /></div>
              </div>
              <div><Label htmlFor="pdesc">Description</Label><Input id="pdesc" name="description" maxLength={1000} /></div>
              <table className="w-full text-left text-sm"><thead className="text-slate-500"><tr><th className="py-1 font-medium">Use</th><th className="py-1 font-medium">Price</th><th className="py-1 font-medium">Included a month</th><th className="py-1 font-medium">Quota a month</th></tr></thead>
                <tbody>{METERS.map(([k, l]) => (
                  <tr key={k}><td className="py-1 pr-2">{l}</td>
                    <td className="py-1 pr-2"><Input name={`${k}.price`} type="number" min="0" step="any" aria-label={`${l} price`} placeholder="Not charged" /></td>
                    <td className="py-1 pr-2"><Input name={`${k}.included`} type="number" min="0" step="any" aria-label={`${l} included`} /></td>
                    <td className="py-1"><Input name={`${k}.cap`} type="number" min="0" step="any" aria-label={`${l} quota`} placeholder="None" /></td></tr>))}</tbody></table>
              <Reason />
            </ActionForm>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="space-y-3 text-sm">
              <h2 className="font-medium">FX rates</h2>
              <p className="text-slate-600">Used only to compare provider cost (billed to XploVoice in the provider&apos;s currency) with tenant charges. Never fetched automatically.</p>
              <ul>{fx.map((r, i) => <li key={i}>1 {r.base} = {Number(r.rate)} {r.quote} · {r.source} · <When iso={r.effective_from} /></li>)}{fx.length === 0 && <li className="text-slate-500">None entered.</li>}</ul>
              <ActionForm action={fxAction} submit="Add rate" variant="secondary" className="space-y-2">
                <div className="grid grid-cols-3 gap-2"><Select name="base" aria-label="From"><option>USD</option><option>INR</option></Select><Select name="quote" aria-label="To"><option>INR</option><option>USD</option></Select>
                  <Input name="rate" type="number" min="0" step="any" required placeholder="Rate" aria-label="Rate" /></div>
                <Input name="source" required minLength={3} maxLength={200} placeholder="Source (for example, the bank's reference rate)" /><Reason />
              </ActionForm>
            </Card>
            <Card className="space-y-3 text-sm">
              <h2 className="font-medium">Tax rates</h2>
              <p className="text-slate-600">Applied to invoices issued from when the rate is added. Without one, invoices show tax as awaiting configuration.</p>
              <ul>{tax.map((r, i) => <li key={i}>{r.country_code}: {r.label} {Number(r.rate_percent)}% · {r.source} · <When iso={r.effective_from} /></li>)}{tax.length === 0 && <li className="text-slate-500">None entered.</li>}</ul>
              <ActionForm action={taxAction} submit="Add tax rate" variant="secondary" className="space-y-2">
                <div className="grid grid-cols-3 gap-2"><Select name="country_code" aria-label="Country"><option value="IN">India</option><option value="US">United States</option></Select>
                  <Input name="label" required minLength={2} maxLength={60} placeholder="Label" aria-label="Label" />
                  <Input name="rate_percent" type="number" min="0" max="50" step="0.001" required placeholder="%" aria-label="Percent" /></div>
                <Input name="source" required minLength={3} maxLength={200} placeholder="Source (for example, your tax adviser's note)" /><Reason />
              </ActionForm>
            </Card>
          </div>
        </>)}
        <Copyright />
      </main>
    </div>
  );
}
