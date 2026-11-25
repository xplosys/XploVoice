// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { api, ApiError, type KbDocument, type KnowledgeBase } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { ActionForm } from "@/components/forms/action-form";
import { KbSearch, UploadForm } from "@/components/forms/phase5";
import { Badge, Card, Input, Label } from "@/components/ui";
import { addTextAction, deleteDocAction, kbStatusAction } from "../../workflow-actions";

export const metadata = { title: "Knowledge base · XploVoice" };

const TONE = { ready: "green", scanning: "slate", processing: "slate", rejected: "red", failed: "amber" } as const;

export default async function KbPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await getMe();
  if (!can(me, "knowledge:read")) redirect("/app");
  const { id } = await params;
  const base = `/v1/knowledge-bases/${encodeURIComponent(id)}`;
  const kb = await api<KnowledgeBase>(base).catch((e) => { if (e instanceof ApiError && e.status === 404) notFound(); throw e; });
  const docs = await api<KbDocument[]>(`${base}/documents`);
  const manage = can(me, "knowledge:manage");
  const active = kb.status === "active";
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link href="/app/knowledge" className="text-sm text-brand-700 underline">Knowledge base</Link>
          <h1 className="flex items-center gap-3 text-2xl font-semibold">{kb.name} {!active && <Badge tone="red">archived</Badge>}</h1>
          <p className="text-sm text-slate-600">{kb.ready_documents} document{kb.ready_documents === 1 ? "" : "s"} ready, {kb.chunks} searchable passages.{!active && " Archived knowledge bases are never searched."}</p>
        </div>
        {manage && <ActionForm action={kbStatusAction} submit={active ? "Archive" : "Restore"} variant="secondary" className="flex gap-2">
          <input type="hidden" name="id" value={kb.id} /><input type="hidden" name="status" value={active ? "archived" : "active"} /></ActionForm>}
      </div>

      <Card>
        <h2 className="mb-2 font-medium">Try a question</h2>
        <p className="mb-3 text-sm text-slate-600">Shows the passages an agent would be given for this question.</p>
        <KbSearch kbId={kb.id} />
      </Card>

      <Card className="p-0">
        <h2 className="px-6 pt-5 font-medium">Documents</h2>
        {docs.length === 0 ? <p className="p-6 text-sm text-slate-600">No documents yet.</p> : (
          <table className="mt-3 w-full table-fixed text-left text-sm">
            <thead className="border-y border-slate-200 text-slate-500"><tr>
              <th className="w-2/5 px-6 py-2 font-medium">Title</th><th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Size</th><th className="w-24 px-4 py-2" /></tr></thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id} className="border-b border-slate-100 align-top last:border-0">
                  <td className="px-6 py-2"><span className="font-medium">{d.title}</span>
                    <p className="truncate text-xs text-slate-500">{d.source === "text" ? "Pasted text" : d.filename} · {new Date(d.created_at).toLocaleDateString()}</p></td>
                  <td className="px-4 py-2"><Badge tone={TONE[d.status]}>{d.status}</Badge>
                    {d.error && <p className="text-xs text-red-700">{d.error}</p>}
                    {d.scan_engine && d.source === "upload" && <p className="text-xs text-slate-500">Scan: {d.scan_engine}, {d.scan_result}</p>}</td>
                  <td className="px-4 py-2 text-slate-600">{(d.size_bytes / 1024).toFixed(1)} KB<br /><span className="text-xs">{d.chunk_count} passages</span></td>
                  <td className="px-4 py-2">{manage && <ActionForm action={deleteDocAction} submit="Remove" variant="ghost" className="">
                    <input type="hidden" name="id" value={kb.id} /><input type="hidden" name="doc" value={d.id} /></ActionForm>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {manage && active && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card><h2 className="mb-3 font-medium">Upload a file</h2><UploadForm kbId={kb.id} />
            <p className="mt-3 text-xs text-slate-500">Every file is scanned for malware and its type is checked from its content. Only the extracted text is kept, never the file.</p></Card>
          <Card><h2 className="mb-3 font-medium">Paste text</h2>
            <ActionForm action={addTextAction} submit="Add">
              <input type="hidden" name="id" value={kb.id} />
              <div><Label htmlFor="title">Title</Label><Input id="title" name="title" required maxLength={200} placeholder="Opening hours and parking" /></div>
              <div><Label htmlFor="text">Text</Label><textarea id="text" name="text" required rows={8} maxLength={200000} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" /></div>
            </ActionForm></Card>
        </div>
      )}
    </div>
  );
}
