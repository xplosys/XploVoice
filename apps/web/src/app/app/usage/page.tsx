// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { fmtQty } from "@/lib/utils";
import { api, type UsageEvent, type UsageRow } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { Badge, Card } from "@/components/ui";
import { When } from "@/components/when";

export const metadata = { title: "Usage · XploVoice" };

const fmtCost = (c: string | null, cur: string | null) => (c && cur ? `${cur} ${Number(c).toFixed(6)}` : "—");

export default async function UsagePage() {
  const me = await getMe();
  if (!can(me, "usage:read")) redirect("/app");
  const [rows, events] = await Promise.all([api<UsageRow[]>("/v1/usage/summary?days=30"), api<UsageEvent[]>("/v1/usage/events?limit=25")]);
  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-semibold">Usage</h1>
        <p className="text-sm text-slate-600">What each provider actually consumed, in its own units, over the last 30 days. Provider cost is shown at the price in force at the time; it is not your invoice. Your charges and invoices are on the <Link className="underline" href="/app/billing">Billing</Link> page.</p></div>
      <Card className="overflow-x-auto p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-slate-500"><tr>
            <th className="px-4 py-3 font-medium">Day</th><th className="px-4 py-3 font-medium">Model</th><th className="px-4 py-3 font-medium">Account</th>
            <th className="px-4 py-3 text-right font-medium">Quantity</th><th className="px-4 py-3 text-right font-medium">Provider cost</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b border-slate-100 last:border-0">
                <td className="px-4 py-2 text-slate-600">{r.day}</td>
                <td className="px-4 py-2">{r.provider} · {r.model} <span className="text-xs uppercase text-slate-500">{r.kind}</span></td>
                <td className="px-4 py-2"><Badge tone={r.account === "customer" ? "brand" : "slate"}>{r.account === "customer" ? "your key" : "XploVoice"}</Badge></td>
                <td className="px-4 py-2 text-right">{fmtQty(r.quantity, r.unit)}</td>
                <td className="px-4 py-2 text-right">{fmtCost(r.cost, r.currency)}{r.unpriced_events > 0 && <span className="block text-xs text-amber-700">{r.unpriced_events} without a price</span>}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-500">No usage yet.</td></tr>}
          </tbody>
        </table>
      </Card>
      {events.length > 0 && (
        <Card className="overflow-x-auto p-0">
          <h2 className="px-4 pt-4 font-medium">Recent events</h2>
          <table className="mt-2 w-full text-left text-sm">
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-t border-slate-100">
                  <td className="whitespace-nowrap px-4 py-2 text-slate-600"><When iso={e.occurred_at} /></td>
                  <td className="px-4 py-2">{e.provider} · {e.model}</td>
                  <td className="px-4 py-2 text-slate-600">{e.source_type}</td>
                  <td className="px-4 py-2 text-right">{fmtQty(e.quantity, e.unit)}</td>
                  <td className="px-4 py-2 text-right">{fmtCost(e.cost, e.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
