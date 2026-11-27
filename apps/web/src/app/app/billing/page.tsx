// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type BillingOverview, type Invoice, type LedgerEntry, type Plan } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { fmtMoney, fmtPrice } from "@/lib/utils";
import { ActionForm } from "@/components/forms/action-form";
import { Badge, Card, Input, Label, Notice } from "@/components/ui";
import { When } from "@/components/when";
import { billingSettingsAction, cancelPlanAction, choosePlanAction, resumePlanAction } from "../billing-actions";

export const metadata = { title: "Billing · XploVoice" };

const SUB_TONE = { trialing: "brand", active: "green", past_due: "red", cancelled: "slate" } as const;
const INV_TONE = { open: "amber", paid: "green", void: "slate" } as const;
const qty = (q: string | number) => Number(q).toLocaleString(undefined, { maximumFractionDigits: 3 });
const LIMIT_LABEL: Record<string, string> = { max_agents: "agents", max_concurrent_calls: "calls at once", max_phone_numbers: "phone numbers" };

function PlanPrices({ plan }: { plan: Plan }) {
  return (
    <ul className="space-y-1 text-sm text-slate-600">
      {plan.prices.map((p) => (
        <li key={p.meter}>
          {p.meter === "base_fee" ? <><span className="font-medium text-slate-800">{fmtMoney(p.unit_price, plan.currency)}</span> a month</>
            : <>{p.label}: {fmtPrice(p.unit_price, plan.currency)} per {p.unit}
              {Number(p.included_quantity) > 0 && <>, {qty(p.included_quantity)} included</>}
              {p.monthly_cap && <>, up to {qty(p.monthly_cap)} a month</>}</>}
        </li>
      ))}
      {plan.prices.length === 0 && <li>No prices set.</li>}
      {Object.entries(plan.limits).map(([k, v]) => <li key={k}>Up to {v} {LIMIT_LABEL[k] ?? k}</li>)}
      {plan.trial_days > 0 && <li>{plan.trial_days}-day trial without the plan fee</li>}
    </ul>
  );
}

export default async function BillingPage() {
  const me = await getMe();
  if (!can(me, "billing:read")) redirect("/app");
  const manage = can(me, "billing:manage");
  const [b, plans, invoices, ledger] = await Promise.all([
    api<BillingOverview>("/v1/billing"),
    api<Plan[]>("/v1/billing/plans"),
    api<Invoice[]>("/v1/billing/invoices"),
    api<LedgerEntry[]>("/v1/billing/ledger?limit=20"),
  ]);
  const sub = b.subscription;
  const cur = b.currency;
  const others = plans.filter((p) => p.id !== sub?.plan.id);
  const limit = b.settings.spend_limit ? Number(b.settings.spend_limit) : null;
  const pct = limit ? Math.min(100, (Number(b.period_total) / limit) * 100) : null;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Billing</h1>
        <p className="text-sm text-slate-600">Your plan, this period&apos;s charges, spending limit and invoices. Charges come from measured use (phone minutes in carrier pulses, AI tokens, speech seconds and characters) at your plan&apos;s prices. Use on your own AI provider keys is not charged here. Amounts are in {cur}.</p>
      </div>
      {b.blocked && <Notice>New calls and AI requests are paused: {b.blocked.message} Calls already in progress are not cut off.</Notice>}

      <Card>
        {sub ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-lg font-medium">{sub.plan.name} <Badge tone={SUB_TONE[sub.status]}>{sub.status.replace("_", " ")}</Badge></h2>
                <p className="text-sm text-slate-600">This period: <When iso={sub.current_period_start} /> to <When iso={sub.current_period_end} />
                  {sub.trial_ends_at && sub.status === "trialing" && <> · trial ends <When iso={sub.trial_ends_at} /></>}</p>
              </div>
              <div className="text-right"><p className="text-xs text-slate-500">Charges so far</p><p className="text-2xl font-semibold">{fmtMoney(b.period_total, cur)}</p></div>
            </div>
            {sub.pending_plan && <p className="text-sm">Changes to <span className="font-medium">{sub.pending_plan.name}</span> when this period ends.</p>}
            {sub.cancel_at_period_end && <p className="text-sm text-red-700">Your plan ends when this period ends.</p>}
            <PlanPrices plan={sub.plan} />
            {manage && (sub.cancel_at_period_end
              ? <ActionForm action={resumePlanAction} submit="Keep my plan" variant="secondary" />
              : <details><summary className="cursor-pointer text-sm text-red-700 underline">Cancel plan</summary>
                  <ActionForm action={cancelPlanAction} submit="End my plan at the end of this period" variant="danger" className="mt-2 space-y-2" /></details>)}
          </div>
        ) : (
          <div><h2 className="text-lg font-medium">No plan yet</h2>
            <p className="text-sm text-slate-600">{plans.length ? "Choose a plan below. Until then your usage is measured but not billed." : "No plans are available yet (awaiting configuration by XploVoice). Your usage is measured but not billed."}</p></div>
        )}
      </Card>

      {sub && (
        <Card className="overflow-x-auto p-0">
          <h2 className="px-6 pt-5 font-medium">This period</h2>
          <table className="mt-2 w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500"><tr>
              <th className="px-6 py-2 font-medium">What</th><th className="px-4 py-2 text-right font-medium">Used</th>
              <th className="px-4 py-2 text-right font-medium">Included</th><th className="px-4 py-2 text-right font-medium">Price</th>
              <th className="px-6 py-2 text-right font-medium">Amount</th></tr></thead>
            <tbody>
              {b.usage.map((u) => (
                <tr key={u.meter} className="border-b border-slate-100 last:border-0">
                  <td className="px-6 py-2">{u.label}{u.monthly_cap && <span className="block text-xs text-slate-500">quota {qty(u.monthly_cap)} {u.unit}{Number(u.quantity) >= Number(u.monthly_cap) && <Badge tone="red">used up</Badge>}</span>}</td>
                  <td className="px-4 py-2 text-right">{u.meter === "base_fee" ? "—" : `${qty(u.quantity)} × ${u.unit}`}</td>
                  <td className="px-4 py-2 text-right">{Number(u.included_quantity) > 0 ? `${qty(u.included_used)} of ${qty(u.included_quantity)}` : "—"}</td>
                  <td className="px-4 py-2 text-right">{u.unit_price === null ? "not charged" : fmtPrice(u.unit_price, cur)}</td>
                  <td className="px-6 py-2 text-right">{fmtMoney(u.amount, cur)}</td>
                </tr>
              ))}
              {b.usage.length === 0 && <tr><td colSpan={5} className="px-6 py-4 text-slate-500">Nothing yet.</td></tr>}
            </tbody>
            <tfoot><tr className="border-t border-slate-200 font-medium"><td className="px-6 py-2" colSpan={4}>Total so far (credits included, before tax)</td>
              <td className="px-6 py-2 text-right">{fmtMoney(b.period_total, cur)}</td></tr></tfoot>
          </table>
        </Card>
      )}

      {(sub ? others : plans).length > 0 && (
        <div className="space-y-2">
          <h2 className="font-medium">{sub ? "Other plans" : "Plans"}</h2>
          {sub && <p className="text-sm text-slate-600">A new plan starts when the current period ends, so each period is billed on one plan.</p>}
          <div className="grid gap-4 md:grid-cols-2">
            {(sub ? others : plans).map((p) => (
              <Card key={p.id} className="space-y-3">
                <div><h3 className="font-medium">{p.name} <Badge>{p.kind === "payg" ? "pay as you go" : "monthly"}</Badge></h3>
                  {p.description && <p className="text-sm text-slate-600">{p.description}</p>}</div>
                <PlanPrices plan={p} />
                {manage && (sub?.pending_plan?.id === p.id ? <p className="text-sm text-slate-600">Starts next period.</p> : (
                  <ActionForm action={choosePlanAction} submit={sub ? "Switch at the end of this period" : "Choose this plan"} variant={sub ? "secondary" : "primary"}>
                    <input type="hidden" name="plan_id" value={p.id} />
                  </ActionForm>))}
              </Card>
            ))}
          </div>
        </div>
      )}

      <Card className="space-y-4">
        <div><h2 className="font-medium">Spending limit and alerts</h2>
          <p className="text-sm text-slate-600">Alerts are recorded once a period as charges reach each level, and sent to your webhooks as <code>billing.alert</code> (email is awaiting configuration). With a hard limit, new calls and AI requests stop at the limit.</p></div>
        {limit && pct !== null && (
          <div>
            <div className="h-2 w-full rounded-full bg-slate-100" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)} aria-label="Spending against the limit">
              <div className={`h-2 rounded-full ${pct >= 100 ? "bg-red-600" : pct >= 80 ? "bg-amber-500" : "bg-brand-600"}`} style={{ width: `${pct}%` }} />
            </div>
            <p className="mt-1 text-xs text-slate-600">{fmtMoney(b.period_total, cur)} of {fmtMoney(limit, cur)} ({Math.round(pct)}%)</p>
          </div>
        )}
        {b.alerts.length > 0 && (
          <ul className="space-y-1 text-sm">{b.alerts.map((a, i) => (
            <li key={i}><Badge tone={a.kind === "quota_reached" || a.threshold >= 100 ? "red" : "amber"}>{a.kind === "quota_reached" ? "quota used up" : `${a.threshold}% of limit`}</Badge> {a.meter ? a.meter.replaceAll("_", " ") : fmtMoney(a.amount, cur)} · <When iso={a.created_at} /></li>
          ))}</ul>
        )}
        {manage ? (
          <ActionForm action={billingSettingsAction} submit="Save">
            <div className="grid gap-3 sm:grid-cols-2">
              <div><Label htmlFor="limit">Monthly spending limit ({cur})</Label><Input id="limit" name="spend_limit" type="number" min="1" step="0.01" defaultValue={b.settings.spend_limit ?? ""} placeholder="No limit" /></div>
              <label className="flex items-center gap-2 pt-6 text-sm"><input type="checkbox" name="hard_limit" defaultChecked={b.settings.hard_limit} /> Stop new calls at the limit</label>
            </div>
            <fieldset><legend className="mb-1 text-sm font-medium text-slate-700">Alert at</legend>
              <div className="flex flex-wrap gap-3 text-sm">{[25, 50, 75, 80, 90, 100].map((p) => (
                <label key={p} className="flex items-center gap-1"><input type="checkbox" name="alert_percents" value={p} defaultChecked={b.settings.alert_percents.includes(p)} /> {p}%</label>
              ))}</div></fieldset>
            <h3 className="pt-2 text-sm font-medium">Invoice details</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <div><Label htmlFor="legal">Legal name</Label><Input id="legal" name="legal_name" maxLength={160} defaultValue={b.settings.legal_name ?? ""} placeholder={me.tenant_name} /></div>
              <div><Label htmlFor="taxid">Tax ID ({cur === "INR" ? "GSTIN" : "EIN"})</Label><Input id="taxid" name="tax_id" maxLength={20} defaultValue={b.settings.tax_id ?? ""} /></div>
              <div><Label htmlFor="bemail">Billing email</Label><Input id="bemail" name="billing_email" type="email" defaultValue={b.settings.billing_email ?? ""} /></div>
              <div><Label htmlFor="addr">Address</Label><Input id="addr" name="address" maxLength={500} defaultValue={b.settings.address ?? ""} /></div>
            </div>
          </ActionForm>
        ) : <p className="text-sm text-slate-600">Limit: {limit ? fmtMoney(limit, cur) : "none"}. Only the owner can change billing.</p>}
      </Card>

      <Card className="p-0">
        <h2 className="px-6 pt-5 font-medium">Invoices</h2>
        {invoices.length === 0 ? <p className="px-6 pb-6 pt-2 text-sm text-slate-600">No invoices yet. One is issued when each period ends.</p> : (
          <ul className="mt-2 divide-y divide-slate-100 text-sm">{invoices.map((i) => (
            <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 px-6 py-3">
              <div><Link className="font-medium underline" href={`/app/billing/invoices/${i.id}`}>{i.number}</Link> <Badge tone={INV_TONE[i.status]}>{i.status}</Badge>
                <p className="text-xs text-slate-500">{i.plan_name} · <When iso={i.period_start} /> to <When iso={i.period_end} />{i.status === "open" && <> · due <When iso={i.due_at} /></>}</p></div>
              <span className="font-medium">{fmtMoney(i.total, i.currency)}</span>
            </li>))}</ul>
        )}
      </Card>

      {ledger.length > 0 && (
        <Card className="overflow-x-auto p-0">
          <h2 className="px-6 pt-5 font-medium">Recent charges</h2>
          <table className="mt-2 w-full text-left text-sm"><tbody>
            {ledger.map((e) => (
              <tr key={e.id} className="border-t border-slate-100">
                <td className="whitespace-nowrap px-6 py-2 text-slate-600"><When iso={e.occurred_at} /></td>
                <td className="px-4 py-2">{e.description}{e.reason && <span className="text-slate-500">: {e.reason}</span>}</td>
                <td className="px-4 py-2 text-right text-slate-600">{e.meter && e.meter !== "base_fee" ? qty(e.quantity) : ""}{Number(e.included_applied) > 0 && <span className="block text-xs">{qty(e.included_applied)} included</span>}</td>
                <td className="px-6 py-2 text-right">{fmtMoney(e.amount, e.currency, Math.abs(Number(e.amount)) < 1 && Number(e.amount) !== 0 ? 4 : 2)}</td>
              </tr>))}
          </tbody></table>
        </Card>
      )}
      <p className="text-xs text-slate-500">Online payment by card or UPI is awaiting a payment gateway contract. {b.payment_providers.some((p) => p.key === "test") && "In development, open invoices can be paid with the test provider, which moves no money."}</p>
    </div>
  );
}
