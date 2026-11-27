// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { api, ApiError, type BillingOverview, type InvoiceDetail } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { fmtMoney, fmtPrice } from "@/lib/utils";
import { ActionForm } from "@/components/forms/action-form";
import { PrintButton } from "@/components/print-button";
import { Badge, Card, Select } from "@/components/ui";
import { When } from "@/components/when";
import { payInvoiceAction } from "../../../billing-actions";

export const metadata = { title: "Invoice · XploVoice" };

const TONE = { open: "amber", paid: "green", void: "slate" } as const;
const qty = (q: string) => Number(q).toLocaleString(undefined, { maximumFractionDigits: 3 });

export default async function InvoicePage({ params }: { params: Promise<{ id: string }> }) {
  const me = await getMe();
  if (!can(me, "billing:read")) redirect("/app");
  const { id } = await params;
  let inv: InvoiceDetail;
  try {
    inv = await api<InvoiceDetail>(`/v1/billing/invoices/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  const b = await api<BillingOverview>("/v1/billing");
  const testPay = b.payment_providers.some((p) => p.key === "test");
  const cur = inv.currency;
  const due = Number(inv.total) - Number(inv.amount_paid);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2 print:hidden">
        <Link className="text-sm underline" href="/app/billing">← Billing</Link>
        <PrintButton />
      </div>
      <Card className="space-y-6">
        <div className="flex flex-wrap justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">Invoice</p>
            <h1 className="text-2xl font-semibold">{inv.number} <Badge tone={TONE[inv.status]}>{inv.status}</Badge></h1>
            <p className="text-sm text-slate-600">Issued <When iso={inv.issued_at} />{inv.status === "open" && <> · due <When iso={inv.due_at} /></>}{inv.paid_at && <> · paid <When iso={inv.paid_at} /></>}</p>
            {inv.void_reason && <p className="text-sm text-slate-600">Voided: {inv.void_reason}</p>}
          </div>
          <div className="text-right text-sm">
            <p className="font-medium">{inv.seller.name}</p><p className="text-slate-600">{inv.seller.product}</p>
          </div>
        </div>
        <div className="grid gap-4 text-sm sm:grid-cols-2">
          <div><p className="text-xs uppercase tracking-wide text-slate-500">Bill to</p>
            <p className="font-medium">{inv.bill_to.name}</p>
            {inv.bill_to.address && <p className="whitespace-pre-line text-slate-600">{inv.bill_to.address}</p>}
            {inv.bill_to.tax_id && <p className="text-slate-600">Tax ID {inv.bill_to.tax_id}</p>}
            {inv.bill_to.email && <p className="text-slate-600">{inv.bill_to.email}</p>}</div>
          <div><p className="text-xs uppercase tracking-wide text-slate-500">Period</p>
            <p>{inv.plan_name} plan · <When iso={inv.period_start} /> to <When iso={inv.period_end} /></p></div>
        </div>
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-slate-500"><tr>
            <th className="py-2 font-medium">Description</th><th className="py-2 text-right font-medium">Quantity</th>
            <th className="py-2 text-right font-medium">Unit price</th><th className="py-2 text-right font-medium">Amount</th></tr></thead>
          <tbody>
            {inv.lines.map((l) => (
              <tr key={l.position} className="border-b border-slate-100">
                <td className="py-2">{l.description}{Number(l.included_quantity) > 0 && <span className="block text-xs text-slate-500">{qty(l.included_quantity)} included in the plan</span>}</td>
                <td className="py-2 text-right">{l.entry_type === "usage" ? qty(l.quantity) : ""}</td>
                <td className="py-2 text-right">{l.unit_price !== null && l.entry_type !== "credit" ? fmtPrice(l.unit_price, cur) : ""}</td>
                <td className="py-2 text-right">{fmtMoney(l.amount, cur)}</td>
              </tr>
            ))}
            {inv.lines.length === 0 && <tr><td colSpan={4} className="py-3 text-slate-500">No charges in this period.</td></tr>}
          </tbody>
          <tfoot className="text-sm">
            <tr><td colSpan={3} className="pt-3 text-right">Subtotal</td><td className="pt-3 text-right">{fmtMoney(inv.subtotal, cur)}</td></tr>
            <tr><td colSpan={3} className="text-right">{inv.tax_label ? `${inv.tax_label} (${Number(inv.tax_percent)}%)` : "Tax (awaiting configuration)"}</td><td className="text-right">{fmtMoney(inv.tax_amount, cur)}</td></tr>
            <tr className="font-semibold"><td colSpan={3} className="text-right">Total</td><td className="text-right">{fmtMoney(inv.total, cur)}</td></tr>
            {Number(inv.amount_paid) > 0 && <tr><td colSpan={3} className="text-right">Paid</td><td className="text-right">{fmtMoney(inv.amount_paid, cur)}</td></tr>}
          </tfoot>
        </table>
        {inv.payments.length > 0 && (
          <div className="text-sm"><h2 className="font-medium">Payments</h2>
            <ul className="mt-1 space-y-1">{inv.payments.map((p) => (
              <li key={p.id}><Badge tone={p.status === "succeeded" ? "green" : p.status === "failed" ? "red" : "amber"}>{p.status}</Badge> {fmtMoney(p.amount, p.currency)} · {p.provider_key === "test" ? "test provider (no money moved)" : p.provider_key} · <When iso={p.created_at} />{p.failure_reason && ` · ${p.failure_reason}`}</li>
            ))}</ul></div>
        )}
      </Card>
      {inv.status === "open" && can(me, "billing:manage") && (
        <Card className="space-y-3 print:hidden">
          <h2 className="font-medium">Pay {fmtMoney(due, cur)}</h2>
          <p className="text-sm text-slate-600">Card and UPI payments are awaiting a payment gateway contract.</p>
          {testPay && (
            <ActionForm action={payInvoiceAction} submit="Pay with the test provider" className="flex flex-wrap items-end gap-3">
              <input type="hidden" name="id" value={inv.id} />
              <div><label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="outcome">Test outcome</label>
                <Select id="outcome" name="outcome" defaultValue="succeed"><option value="succeed">Payment succeeds</option><option value="decline">Card declined</option></Select></div>
            </ActionForm>
          )}
        </Card>
      )}
    </div>
  );
}
