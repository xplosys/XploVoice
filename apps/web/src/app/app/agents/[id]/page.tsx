// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { api, ApiError, type Agent, type AgentVersion } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { Button, Card } from "@/components/ui";
import { AgentForm } from "@/components/forms/agent-form";
import { archiveAgentAction } from "../actions";

export const metadata = { title: "Voice agent · XploVoice" };

export default async function AgentPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await getMe();
  if (!can(me, "agents:read")) redirect("/app");
  const { id } = await params;
  const agent = await api<Agent>(`/v1/agents/${encodeURIComponent(id)}`).catch((e) => {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  });
  const versions = await api<AgentVersion[]>(`/v1/agents/${encodeURIComponent(id)}/versions`);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/app/agents" className="text-sm text-brand-700 underline">Voice agents</Link>
          <h1 className="text-2xl font-semibold">{agent.name}</h1>
        </div>
        {can(me, "calls:test") && <Link href={`/app/agents/${agent.id}/call`} className="rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700">Test call</Link>}
      </div>
      <Card><AgentForm agent={agent} canEdit={can(me, "agents:manage")} /></Card>
      <Card>
        <h2 className="mb-2 font-medium">Versions</h2>
        <ul className="text-sm text-slate-600">
          {versions.map((v) => <li key={v.id}>Version {v.version} · {new Date(v.created_at).toLocaleString()}{v.id === agent.version_id ? " (current)" : ""}</li>)}
        </ul>
      </Card>
      {can(me, "agents:manage") && (
        <form action={archiveAgentAction}><input type="hidden" name="id" value={agent.id} />
          <Button type="submit" variant="ghost" className="text-red-700">Archive this agent</Button></form>
      )}
    </div>
  );
}
