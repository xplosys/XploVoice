// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { api, ApiError, type Agent, type AgentVersion, type Publication, type Readiness } from "@/lib/api";
import { modelOptions, STATUS } from "@/lib/agents";
import { can, getMe } from "@/lib/me";
import { Badge, Card } from "@/components/ui";
import { AgentBuilder } from "@/components/forms/agent-builder";
import { LifecyclePanel, VersionAction } from "@/components/forms/agent-lifecycle";

export const metadata = { title: "Voice agent · XploVoice" };

const ACTION: Record<string, string> = {
  publish: "Published", rollback: "Rolled back to", pause: "Paused", resume: "Resumed", archive: "Archived", restore: "Restored",
};
const LEVEL = { error: "red", warning: "amber", ok: "green" } as const;

export default async function AgentPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await getMe();
  if (!can(me, "agents:read")) redirect("/app");
  const { id } = await params;
  const base = `/v1/agents/${encodeURIComponent(id)}`;
  const agent = await api<Agent>(base).catch((e) => {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  });
  const [versions, readiness, history, models] = await Promise.all([
    api<AgentVersion[]>(`${base}/versions`), api<Readiness>(`${base}/readiness`), api<Publication[]>(`${base}/history`),
    modelOptions(),
  ]);
  const st = STATUS[agent.status];
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link href="/app/agents" className="text-sm text-brand-700 underline">Voice agents</Link>
          <h1 className="flex items-center gap-3 text-2xl font-semibold">{agent.name} <Badge tone={st.tone}>{st.label}</Badge></h1>
          <p className="text-sm text-slate-600">
            Latest version {agent.version}
            {agent.published_version ? `. Live callers reach version ${agent.published_version}` : ". Not published yet"}
            {agent.has_unpublished_changes ? ", and the latest changes aren't published." : "."}
          </p>
        </div>
        {can(me, "calls:test") && agent.status !== "archived" && <Link href={`/app/agents/${agent.id}/call`} className="rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700">Test call</Link>}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_22rem]">
        <Card><AgentBuilder key={agent.version_id} agent={agent} models={models} canEdit={can(me, "agents:manage") && agent.status !== "archived"} /></Card>
        <div className="space-y-6">
          <Card>
            <h2 className="mb-2 font-medium">Ready to publish? (version {readiness.version})</h2>
            <ul className="mb-4 space-y-2 text-sm">
              <li className="flex items-start gap-2"><span className="shrink-0"><Badge tone={readiness.tested ? "green" : "amber"}>{readiness.tested ? "ok" : "to do"}</Badge></span>
                <span>{readiness.tested ? "Tested: a test call on this version completed." : "Make a test call on this version."}</span></li>
              {readiness.checks.map((c) => (
                <li key={c.key} className="flex items-start gap-2"><span className="shrink-0"><Badge tone={LEVEL[c.level]}>{c.level}</Badge></span><span>{c.message}</span></li>
              ))}
            </ul>
            <LifecyclePanel agent={agent} readiness={readiness} canPublish={can(me, "agents:publish")}
              canManage={can(me, "agents:manage")} canSkipTest={can(me, "tenant:manage")} />
          </Card>
          <Card>
            <h2 className="mb-2 font-medium">Versions</h2>
            <ul className="space-y-3 text-sm">
              {versions.map((v) => (
                <li key={v.id} className="border-b border-slate-100 pb-3 last:border-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link href={`/app/agents/${agent.id}/versions/${v.version}`} className="font-medium text-brand-700 underline">Version {v.version}</Link>
                    {v.is_published && <Badge tone="green">live</Badge>}
                    {!v.is_published && v.was_published && <Badge>was live</Badge>}
                    {v.id === agent.version_id && <Badge tone="brand">latest</Badge>}
                  </div>
                  <p className="text-xs text-slate-500">{new Date(v.created_at).toLocaleString()}{v.created_by ? ` · ${v.created_by}` : ""} · {v.test_calls} test call{v.test_calls === 1 ? "" : "s"}</p>
                  {v.note && <p className="text-xs text-slate-600">{v.note}</p>}
                  {can(me, "agents:publish") && <div className="mt-1"><VersionAction agent={agent} v={v} /></div>}
                </li>
              ))}
            </ul>
          </Card>
          <Card>
            <h2 className="mb-2 font-medium">Publishing history</h2>
            {history.length === 0 ? <p className="text-sm text-slate-600">Nothing published yet.</p> : (
              <ul className="space-y-2 text-sm">
                {history.map((h, i) => (
                  <li key={i}>
                    <span className="font-medium">{ACTION[h.action] ?? h.action}{h.version ? ` version ${h.version}` : ""}</span>
                    <span className="text-xs text-slate-500"> · {new Date(h.created_at).toLocaleString()}{h.actor ? ` · ${h.actor}` : ""}</span>
                    {h.reason && <p className="text-xs text-slate-600">{h.reason}</p>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
