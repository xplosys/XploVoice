// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { api, ApiError, type Agent, type AgentVersion } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { TestCall } from "@/components/voice/test-call";
import { ChatTest } from "@/components/forms/phase5";
import { Card } from "@/components/ui";

export const metadata = { title: "Test call · XploVoice" };

export default async function CallAgentPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await getMe();
  if (!can(me, "calls:test")) redirect("/app");
  const { id } = await params;
  const base = `/v1/agents/${encodeURIComponent(id)}`;
  const agent = await api<Agent>(base).catch((e) => {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  });
  const versions = await api<AgentVersion[]>(`${base}/versions`);
  return (
    <div className="space-y-6">
      <div>
        <Link href={`/app/agents/${agent.id}`} className="text-sm text-brand-700 underline">{agent.name}</Link>
        <h1 className="text-2xl font-semibold">Browser test call</h1>
        <p className="text-sm text-slate-600">Test any saved version (the latest is version {agent.version}). The call uses your AI provider settings and the same voice engine as phone calls, and its usage is metered like any call. A completed test call on a version lets you publish it.</p>
      </div>
      <TestCall agentId={agent.id} agentName={agent.name} latest={agent.version_id}
        versions={versions.map((v) => ({ id: v.id, version: v.version }))} hasHours={agent.config.business_hours.enabled} />
      <Card>
        <h2 className="mb-2 font-medium">Text chat test (latest version)</h2>
        <ChatTest agentId={agent.id} versionId={agent.version_id} />
      </Card>
    </div>
  );
}
