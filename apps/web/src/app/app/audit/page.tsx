// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type AuditEvent } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { Badge, Card } from "@/components/ui";
import { When } from "@/components/when";

export const metadata = { title: "Audit log · XploVoice" };
const PAGE = 50;

export default async function AuditPage({ searchParams }: { searchParams: Promise<{ before?: string }> }) {
  const me = await getMe();
  if (!can(me, "audit:read")) redirect("/app");
  const { before } = await searchParams;
  const b = before && /^\d+$/.test(before) ? `&before_id=${before}` : "";
  const rows = await api<AuditEvent[]>(`/v1/audit-logs?limit=${PAGE}${b}`);
  const tone = (r: string) => (r === "denied" || r === "failure" ? "red" : "green");
  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-semibold">Audit log</h1>
        <p className="text-sm text-slate-600">Append-only and tamper-evident. Secrets and message content are never recorded.</p></div>
      <Card className="overflow-x-auto p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-slate-500"><tr>
            <th className="px-4 py-3 font-medium">Time</th><th className="px-4 py-3 font-medium">Action</th>
            <th className="px-4 py-3 font-medium">Actor</th><th className="px-4 py-3 font-medium">Resource</th>
            <th className="px-4 py-3 font-medium">Result</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-slate-100 last:border-0">
                <td className="whitespace-nowrap px-4 py-2 text-slate-600"><When iso={r.created_at} /></td>
                <td className="px-4 py-2 font-mono text-xs">{r.action}</td>
                <td className="px-4 py-2 text-slate-600">{r.actor_kind}{r.actor_user_id === me.user_id ? " (you)" : ""}</td>
                <td className="px-4 py-2 text-slate-600">{r.resource_type ?? "—"}</td>
                <td className="px-4 py-2"><Badge tone={tone(r.result)}>{r.result}</Badge></td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-500">No events yet.</td></tr>}
          </tbody>
        </table>
      </Card>
      {rows.length === PAGE && (
        <Link className="text-sm text-brand-700 underline" href={`/app/audit?before=${rows[rows.length - 1].id}`}>Older events</Link>
      )}
    </div>
  );
}
