// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type ToolExecution, type ToolInfo } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { EXEC_TONE, label } from "@/lib/tones";
import { ActionForm } from "@/components/forms/action-form";
import { Badge, Card, Input } from "@/components/ui";
import { decisionAction, toolPolicyAction } from "../workflow-actions";
import { When } from "@/components/when";

export const metadata = { title: "Business tools · XploVoice" };

const brief = (o: Record<string, unknown> | null) =>
  o ? Object.entries(o).filter(([, v]) => v !== null && v !== "").map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join(" · ") : "";

export default async function ToolsPage() {
  const me = await getMe();
  if (!can(me, "agents:read")) redirect("/app");
  const seeRuns = can(me, "calls:read");
  const [tools, pending, recent] = await Promise.all([
    api<ToolInfo[]>("/v1/tools"),
    seeRuns ? api<ToolExecution[]>("/v1/tools/executions?status=pending_approval") : Promise.resolve([]),
    seeRuns ? api<ToolExecution[]>("/v1/tools/executions?limit=50") : Promise.resolve([]),
  ]);
  const manage = can(me, "tools:manage");
  const approve = can(me, "tools:approve");
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Business tools</h1>
        <p className="text-sm text-slate-600">Actions an agent can take on a call. An agent can use a tool only when it is switched on here and granted on the agent&apos;s version. Every use is checked, recorded and audited, and tools that need approval wait for a person.</p>
      </div>

      {seeRuns && (
        <Card className="p-0">
          <h2 className="px-6 pt-5 font-medium">Waiting for approval {pending.length > 0 && <Badge tone="amber">{pending.length}</Badge>}</h2>
          {pending.length === 0 ? <p className="p-6 text-sm text-slate-600">Nothing is waiting.</p> : (
            <ul className="mt-2 divide-y divide-slate-100 text-sm">
              {pending.map((e) => (
                <li key={e.id} className="flex flex-wrap items-center justify-between gap-3 px-6 py-3">
                  <div>
                    <p className="font-medium">{e.label}</p>
                    <p className="text-xs text-slate-600">{brief(e.input)}</p>
                    <p className="text-xs text-slate-500"><When iso={e.created_at} />{e.call_id && <> · <Link className="underline" href={`/app/calls/${e.call_id}`}>call</Link></>}</p>
                  </div>
                  {approve && <div className="flex items-center gap-2">
                    <ActionForm action={decisionAction} submit="Approve" className=""><input type="hidden" name="id" value={e.id} /><input type="hidden" name="decision" value="approve" /></ActionForm>
                    <ActionForm action={decisionAction} submit="Deny" variant="danger" className="flex items-center gap-2">
                      <input type="hidden" name="id" value={e.id} /><input type="hidden" name="decision" value="deny" />
                      <Input aria-label="Reason" name="reason" placeholder="Reason (optional)" maxLength={300} className="w-44 py-1" />
                    </ActionForm>
                  </div>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <Card className="p-0">
        <h2 className="px-6 pt-5 font-medium">Tools</h2>
        <ul className="mt-2 divide-y divide-slate-100 text-sm">
          {tools.map((t) => (
            <li key={t.key} className="flex flex-wrap items-center justify-between gap-3 px-6 py-3">
              <div className="max-w-xl">
                <p className="font-medium">{t.label} <span className="font-mono text-xs font-normal text-slate-500">{t.key}</span></p>
                <p className="text-slate-600">{t.description}</p>
              </div>
              {manage ? (
                <ActionForm action={toolPolicyAction} submit="Save" variant="secondary" className="flex items-center gap-3">
                  <input type="hidden" name="key" value={t.key} />
                  <label className="flex items-center gap-1"><input type="checkbox" name="enabled" defaultChecked={t.enabled} /> On</label>
                  <label className="flex items-center gap-1"><input type="checkbox" name="require_approval" defaultChecked={t.require_approval} /> Needs approval</label>
                </ActionForm>
              ) : (
                <div className="flex gap-2"><Badge tone={t.enabled ? "green" : "slate"}>{t.enabled ? "on" : "off"}</Badge>{t.require_approval && <Badge tone="amber">needs approval</Badge>}</div>
              )}
            </li>
          ))}
        </ul>
      </Card>

      {seeRuns && (
        <Card className="p-0">
          <h2 className="px-6 pt-5 font-medium">Recent uses</h2>
          {recent.length === 0 ? <p className="p-6 text-sm text-slate-600">No tool has been used yet.</p> : (
            <table className="mt-2 w-full text-sm">
              <thead className="border-b border-slate-200 text-left text-xs uppercase text-slate-500">
                <tr><th className="px-6 py-2">When</th><th className="px-3 py-2">Tool</th><th className="px-3 py-2">Result</th><th className="px-3 py-2">Details</th><th className="px-3 py-2">Time</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {recent.map((e) => (
                  <tr key={e.id} className="align-top">
                    <td className="px-6 py-2 text-slate-500"><When iso={e.created_at} />{e.call_id && <> · <Link className="underline" href={`/app/calls/${e.call_id}`}>call</Link></>}</td>
                    <td className="px-3 py-2">{e.label}</td>
                    <td className="px-3 py-2"><Badge tone={EXEC_TONE[e.status] ?? "slate"}>{label(e.status)}</Badge></td>
                    <td className="max-w-md px-3 py-2 text-xs text-slate-600">{e.error ?? e.decision_reason ?? brief(e.result)}</td>
                    <td className="px-3 py-2 text-xs">{e.latency_ms != null ? `${e.latency_ms} ms` : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}
    </div>
  );
}
