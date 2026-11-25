// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { api, ApiError, type Agent } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { TestCall } from "@/components/voice/test-call";

export const metadata = { title: "Test call · XploVoice" };

export default async function CallAgentPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await getMe();
  if (!can(me, "calls:test")) redirect("/app");
  const { id } = await params;
  const agent = await api<Agent>(`/v1/agents/${encodeURIComponent(id)}`).catch((e) => {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  });
  return (
    <div className="space-y-6">
      <div>
        <Link href={`/app/agents/${agent.id}`} className="text-sm text-brand-700 underline">{agent.name}</Link>
        <h1 className="text-2xl font-semibold">Browser test call</h1>
        <p className="text-sm text-slate-600">This call uses version {agent.version} of the agent, your AI provider settings and the same voice engine as phone calls. Its usage is metered like any call.</p>
      </div>
      <TestCall agentId={agent.id} agentName={agent.name} />
    </div>
  );
}
