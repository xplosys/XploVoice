// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type AgentTemplate } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { Card } from "@/components/ui";
import { NewAgentForm } from "@/components/forms/agent-lifecycle";

export const metadata = { title: "New agent · XploVoice" };

export default async function NewAgentPage() {
  const me = await getMe();
  if (!can(me, "agents:manage")) redirect("/app/agents");
  const templates = await api<AgentTemplate[]>("/v1/agent-templates");
  return (
    <div className="space-y-6">
      <div>
        <Link href="/app/agents" className="text-sm text-brand-700 underline">Voice agents</Link>
        <h1 className="text-2xl font-semibold">New agent</h1>
      </div>
      <Card><NewAgentForm templates={templates} /></Card>
    </div>
  );
}
