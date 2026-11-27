// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type PhiAccessRow } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { Badge, Button, Card, Input, Select } from "@/components/ui";
import { When } from "@/components/when";
import { HealthcareTabs } from "../tabs";

export const metadata = { title: "PHI access log · XploVoice" };

const label = (s: string) => s.replaceAll("_", " ");

export default async function AccessLogPage({ searchParams }: { searchParams: Promise<{ resource_id?: string; result?: string }> }) {
  const me = await getMe();
  if (!can(me, "phi_audit:read")) redirect("/app");
  const { resource_id, result } = await searchParams;
  const q = new URLSearchParams();
  if (resource_id) q.set("resource_id", resource_id);
  if (result === "allowed" || result === "denied") q.set("result", result);
  const rows = await api<PhiAccessRow[]>(`/v1/audit/phi-access?${q}`);
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">PHI access log</h1>
        <p className="text-sm text-slate-600">Every time someone opened health information, or was refused, with the record&apos;s id and the request&apos;s correlation id. Entries can&apos;t be changed or deleted, and they hold no PHI themselves.</p>
      </div>
      <HealthcareTabs me={me} current="/app/healthcare/access-log" />
      <form className="flex flex-wrap gap-2">
        <Input name="resource_id" defaultValue={resource_id} placeholder="Record id (for example a call id)" className="max-w-sm" />
        <Select name="result" defaultValue={result ?? ""} className="max-w-[10rem]" aria-label="Result">
          <option value="">All results</option><option value="allowed">Allowed</option><option value="denied">Refused</option>
        </Select>
        <Button type="submit" variant="secondary">Filter</Button>
      </form>
      <Card className="overflow-x-auto p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-slate-500"><tr>
            <th className="px-4 py-2">When</th><th className="px-4 py-2">Who</th><th className="px-4 py-2">Action</th>
            <th className="px-4 py-2">Record</th><th className="px-4 py-2">Purpose</th><th className="px-4 py-2">Result</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-slate-100 align-top">
                <td className="px-4 py-2 whitespace-nowrap"><When iso={r.occurred_at} /></td>
                <td className="px-4 py-2 font-mono text-xs">{r.actor_kind === "user" ? r.actor_user_id?.slice(0, 8) : r.actor_kind}</td>
                <td className="px-4 py-2">{label(r.action)}</td>
                <td className="px-4 py-2">{label(r.resource_type)}{r.resource_id && <> · {r.resource_type.startsWith("call") ? <Link className="font-mono text-xs underline" href={`/app/calls/${r.resource_id}`}>{r.resource_id.slice(0, 8)}</Link> : <span className="font-mono text-xs">{r.resource_id.slice(0, 8)}</span>}</>}</td>
                <td className="px-4 py-2 text-slate-600">{r.purpose}</td>
                <td className="px-4 py-2">{r.result === "allowed" ? <Badge tone="green">allowed</Badge> : <Badge tone="red">refused</Badge>}{r.reason && <div className="text-xs text-slate-500">{r.reason}</div>}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-slate-500">No entries.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
