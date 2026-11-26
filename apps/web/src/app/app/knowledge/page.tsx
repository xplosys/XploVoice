// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type KnowledgeBase } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { ActionForm } from "@/components/forms/action-form";
import { Badge, Card, Input, Label, Notice } from "@/components/ui";
import { createKbAction } from "../workflow-actions";

export const metadata = { title: "Knowledge base · XploVoice" };

export default async function KnowledgePage() {
  const me = await getMe();
  if (!can(me, "knowledge:read")) redirect("/app");
  const kbs = await api<KnowledgeBase[]>("/v1/knowledge-bases");
  const scanner = kbs[0]?.scanner;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Knowledge base</h1>
        <p className="text-sm text-slate-600">Documents your agents answer questions from. Each agent only searches the knowledge bases you attach to it, and only within your organisation.</p>
      </div>
      {scanner === "builtin-dev" && <Notice>Development scanner in use: uploads are checked for the EICAR test file and executables only. Production requires ClamAV (XV_CLAMAV_URL); without it, uploads are refused.</Notice>}
      <Card className="p-0">
        {kbs.length === 0 ? <p className="p-6 text-sm text-slate-600">No knowledge bases yet.</p> : (
          <ul className="divide-y divide-slate-100">
            {kbs.map((k) => (
              <li key={k.id} className="flex flex-wrap items-center justify-between gap-2 px-6 py-3">
                <div><Link href={`/app/knowledge/${k.id}`} className="font-medium text-brand-700 underline">{k.name}</Link>
                  {k.description && <p className="text-xs text-slate-500">{k.description}</p>}</div>
                <div className="flex items-center gap-3 text-sm text-slate-600">
                  <span>{k.ready_documents} of {k.documents} document{k.documents === 1 ? "" : "s"} ready · {k.chunks} passage{k.chunks === 1 ? "" : "s"}</span>
                  {k.status === "archived" && <Badge tone="red">archived</Badge>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {can(me, "knowledge:manage") && (
        <Card>
          <h2 className="mb-3 font-medium">New knowledge base</h2>
          <ActionForm action={createKbAction} submit="Create">
            <div className="grid gap-4 sm:grid-cols-2">
              <div><Label htmlFor="name">Name</Label><Input id="name" name="name" required maxLength={120} placeholder="Clinic FAQ" /></div>
              <div><Label htmlFor="description">Description (optional)</Label><Input id="description" name="description" maxLength={500} /></div>
            </div>
          </ActionForm>
        </Card>
      )}
    </div>
  );
}
