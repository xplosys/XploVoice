// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type Agent } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { Badge, Card } from "@/components/ui";
import { AgentForm } from "@/components/forms/agent-form";

export const metadata = { title: "Voice agents · XploVoice" };
const LANG: Record<string, string> = { "en-IN": "English (India)", "hi-IN": "Hindi", "hi-Latn-IN": "Hinglish", "en-US": "English (US)" };

export default async function AgentsPage() {
  const me = await getMe();
  if (!can(me, "agents:read")) redirect("/app");
  const agents = await api<Agent[]>("/v1/agents");
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Voice agents</h1>
        <p className="text-sm text-slate-600">Set up an agent and talk to it from your browser. Every save is a new version, and each call keeps the version it started with. The full agent builder, with templates and publishing, arrives in Phase 4.</p>
      </div>
      {agents.length > 0 && (
        <Card className="p-0">
          <ul className="divide-y divide-slate-100">
            {agents.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 px-6 py-4">
                <div>
                  <Link href={`/app/agents/${a.id}`} className="font-medium text-brand-700 underline">{a.name}</Link>
                  <p className="text-xs text-slate-500">{LANG[a.config.language]} · version {a.version}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone="green">{a.status}</Badge>
                  {can(me, "calls:test") && <Link href={`/app/agents/${a.id}/call`} className="rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700">Test call</Link>}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {can(me, "agents:manage") && (
        <Card>
          <h2 className="mb-3 font-medium">{agents.length ? "Add another agent" : "Create your first agent"}</h2>
          <AgentForm canEdit />
        </Card>
      )}
    </div>
  );
}
