// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type Agent } from "@/lib/api";
import { LANG, STATUS } from "@/lib/agents";
import { can, getMe } from "@/lib/me";
import { Badge, Card } from "@/components/ui";

export const metadata = { title: "Voice agents · XploVoice" };

export default async function AgentsPage({ searchParams }: { searchParams: Promise<{ archived?: string }> }) {
  const me = await getMe();
  if (!can(me, "agents:read")) redirect("/app");
  const showArchived = (await searchParams).archived === "1";
  const agents = await api<Agent[]>(`/v1/agents${showArchived ? "?include_archived=true" : ""}`);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Voice agents</h1>
          <p className="text-sm text-slate-600">Build an agent, test it from your browser, then publish it. Every save is a new version. Live callers only reach the published version, and each call keeps the version it started with.</p>
        </div>
        {can(me, "agents:manage") && <Link href="/app/agents/new" className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">New agent</Link>}
      </div>
      {agents.length === 0 ? (
        <Card><p className="text-sm text-slate-600">No agents yet.{can(me, "agents:manage") && <> <Link href="/app/agents/new" className="text-brand-700 underline">Create one from a template</Link>.</>}</p></Card>
      ) : (
        <Card className="p-0">
          <ul className="divide-y divide-slate-100">
            {agents.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 px-6 py-4">
                <div>
                  <Link href={`/app/agents/${a.id}`} className="font-medium text-brand-700 underline">{a.name}</Link>
                  <p className="text-xs text-slate-500">
                    {LANG[a.config.language]} · latest version {a.version}
                    {a.published_version ? ` · live: version ${a.published_version}` : ""}
                    {a.has_unpublished_changes ? " · unpublished changes" : ""}
                  </p>
                  {a.description && <p className="text-xs text-slate-600">{a.description}</p>}
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={STATUS[a.status].tone}>{STATUS[a.status].label}</Badge>
                  {can(me, "calls:test") && a.status !== "archived" && <Link href={`/app/agents/${a.id}/call`} className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium hover:bg-slate-50">Test call</Link>}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Link href={showArchived ? "/app/agents" : "/app/agents?archived=1"} className="text-sm text-slate-600 underline">{showArchived ? "Hide archived agents" : "Show archived agents"}</Link>
    </div>
  );
}
