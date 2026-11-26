// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type CallRow } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { Badge, Card } from "@/components/ui";
import { callTone } from "@/lib/utils";
import { STATE_TONE, label } from "@/lib/tones";
import { When } from "@/components/when";

export const metadata = { title: "Calls · XploVoice" };


export default async function CallsPage() {
  const me = await getMe();
  if (!can(me, "calls:read")) redirect("/app");
  const calls = await api<CallRow[]>("/v1/calls?limit=100");
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Calls</h1>
        <p className="text-sm text-slate-600">Phone calls (inbound and campaign), browser test calls and text chats.</p>
      </div>
      <Card className="overflow-x-auto p-0">
        {calls.length === 0 ? <p className="p-6 text-sm text-slate-600">No calls yet. Start one from a voice agent.</p> : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500"><tr>
              <th className="px-6 py-2 font-medium">Started</th><th className="px-4 py-2 font-medium">Agent</th>
              <th className="px-4 py-2 font-medium">Channel</th><th className="px-4 py-2 font-medium">Number</th><th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 text-right font-medium">Length</th></tr></thead>
            <tbody>
              {calls.map((c) => (
                <tr key={c.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-6 py-2"><Link className="text-brand-700 underline" href={`/app/calls/${c.id}`}><When iso={c.created_at} /></Link></td>
                  <td className="px-4 py-2">{c.agent_name} <span className="text-xs text-slate-500">v{c.agent_version}</span></td>
                  <td className="px-4 py-2">{c.channel === "browser" ? "Browser test" : c.channel === "chat" ? "Text chat" : c.direction === "inbound" ? "Phone, inbound" : "Phone, outbound"}</td>
                  <td className="px-4 py-2 font-mono text-xs">{c.channel === "sip" ? (c.direction === "inbound" ? c.from_number : c.to_number) ?? "–" : "–"}</td>
                  <td className="px-4 py-2">{c.channel === "sip" ? <Badge tone={STATE_TONE[c.state] ?? "slate"}>{label(c.state)}</Badge> : <Badge tone={callTone(c.status)}>{c.status}</Badge>}{c.end_reason && <span className="ml-2 text-xs text-slate-500">{c.end_reason.replace("_", " ")}</span>}</td>
                  <td className="px-4 py-2 text-right">{c.duration_seconds ? `${Number(c.duration_seconds).toFixed(0)} s` : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
