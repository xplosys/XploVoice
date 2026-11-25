// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
// Interactive pieces of the Phase 5 screens: file upload, knowledge search, the typed test chat, and the
// one-time webhook secret.
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";
import { searchKbAction, sendChatAction, startChatAction, uploadDocAction } from "@/app/app/workflow-actions";
import type { ActionState } from "@/lib/actions";
import type { ChatReply, KbHit } from "@/lib/api";
import { Badge, Button, FormError, Input, Label } from "@/components/ui";
import { ActionForm } from "./action-form";

const MAX = 5 * 1024 * 1024;

export function UploadForm({ kbId }: { kbId: string }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [state, setState] = useState<ActionState>();
  const [pending, start] = useTransition();

  function submit() {
    const file = input.current?.files?.[0];
    if (!file) return setState({ error: "Choose a file first." });
    if (file.size > MAX) return setState({ error: "Files can be at most 5 MB." });
    start(async () => {
      const buf = new Uint8Array(await file.arrayBuffer());
      let bin = "";
      for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
      const r = await uploadDocAction(kbId, file.name, btoa(bin), title);
      setState(r);
      if (r?.ok) {
        setTitle("");
        if (input.current) input.current.value = "";
        router.refresh();
      }
    });
  }

  return (
    <div className="space-y-3">
      <div><Label htmlFor="file">File (PDF, Word .docx, text, Markdown or CSV, up to 5 MB)</Label>
        <input id="file" ref={input} type="file" accept=".pdf,.docx,.txt,.md,.csv,text/plain,application/pdf" className="block w-full text-sm" /></div>
      <div><Label htmlFor="utitle">Title (optional)</Label><Input id="utitle" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} /></div>
      <FormError message={state?.error} />
      {state?.ok && <p role="status" className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{state.ok} See the status in the list below.</p>}
      <Button type="button" onClick={submit} disabled={pending}>{pending ? "Scanning and indexing…" : "Upload"}</Button>
    </div>
  );
}

export function KbSearch({ kbId }: { kbId: string }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<KbHit[] | null>(null);
  const [error, setError] = useState<string>();
  const [pending, start] = useTransition();
  return (
    <div className="space-y-3">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); start(async () => {
        const r = await searchKbAction(kbId, q); setError(r.error); setHits(r.hits ?? null); }); }}>
        <Input aria-label="Question" placeholder="Ask what a caller might ask, e.g. Is parking free?" value={q} onChange={(e) => setQ(e.target.value)} maxLength={500} />
        <Button type="submit" variant="secondary" disabled={pending || !q.trim()}>{pending ? "…" : "Search"}</Button>
      </form>
      <FormError message={error} />
      {hits && (hits.length === 0 ? <p className="text-sm text-slate-600">Nothing matched. The agent would say it doesn&apos;t have that information.</p> : (
        <ol className="space-y-2 text-sm">
          {hits.map((h, i) => (
            <li key={i} className="rounded-md border border-slate-200 p-3">
              <div className="mb-1 flex items-center gap-2 text-xs text-slate-500"><span className="font-medium text-slate-700">{h.document}</span> · score {h.score.toFixed(3)}</div>
              <p className="whitespace-pre-wrap">{h.content}</p>
            </li>
          ))}
        </ol>
      ))}
    </div>
  );
}

type Line = { who: "caller" | "agent" | "note"; text: string; tools?: ChatReply["tools"]; sources?: string[] };
const TOOL_TONE: Record<string, "green" | "amber" | "red" | "slate"> = {
  succeeded: "green", pending_approval: "amber", failed: "red", rejected: "red",
};

/** A typed conversation with the agent: the same knowledge search and business tools as a call, without speech. */
export function ChatTest({ agentId, versionId }: { agentId: string; versionId?: string }) {
  const [callId, setCallId] = useState<string>();
  const [lines, setLines] = useState<Line[]>([]);
  const [text, setText] = useState("");
  const [error, setError] = useState<string>();
  const [ended, setEnded] = useState(false);
  const [pending, start] = useTransition();

  function begin() {
    setError(undefined); setEnded(false);
    start(async () => {
      const r = await startChatAction(agentId, versionId);
      if (r.error || !r.chat) return setError(r.error ?? "Could not start the chat.");
      setCallId(r.chat.call_id);
      setLines(r.chat.greeting ? [{ who: "agent", text: r.chat.greeting }] : []);
    });
  }

  function send(e: React.FormEvent) {
    e.preventDefault();
    const said = text.trim();
    if (!said || !callId) return;
    setText(""); setError(undefined);
    setLines((l) => [...l, { who: "caller", text: said }]);
    start(async () => {
      const r = await sendChatAction(callId, said);
      if (r.error || !r.reply) return setError(r.error ?? "No reply.");
      const rep = r.reply;
      setLines((l) => [...l, { who: "agent", text: rep.reply, tools: rep.tools, sources: [...new Set(rep.retrieval.map((x) => x.document))] }]);
      if (rep.ended) { setEnded(true); setLines((l) => [...l, { who: "note", text: `Chat ended (${rep.end_reason?.replace("_", " ")}). A ticket was created for your team.` }]); }
    });
  }

  if (!callId) return (
    <div className="space-y-2">
      <p className="text-sm text-slate-600">Type as a caller would. The agent uses its knowledge bases and business tools exactly as on a call, and anything it books or creates is real (in this organisation). A typed chat doesn&apos;t count as the voice test call needed to publish.</p>
      <FormError message={error} />
      <Button type="button" variant="secondary" onClick={begin} disabled={pending}>{pending ? "Starting…" : "Start a text chat"}</Button>
    </div>
  );
  return (
    <div className="space-y-3">
      <ol className="max-h-[28rem] space-y-2 overflow-y-auto rounded-md bg-slate-50 p-3 text-sm" aria-live="polite">
        {lines.map((l, i) => l.who === "note" ? <li key={i} className="text-center text-xs text-slate-500">{l.text}</li> : (
          <li key={i} className={l.who === "caller" ? "ml-10 rounded-lg bg-brand-600 px-3 py-2 text-white" : "mr-10 rounded-lg border border-slate-200 bg-white px-3 py-2"}>
            <p className="whitespace-pre-wrap">{l.text}</p>
            {!!l.tools?.length && <div className="mt-2 flex flex-wrap gap-1">{l.tools.map((t, j) => <Badge key={j} tone={TOOL_TONE[t.status] ?? "slate"}>{t.name.replaceAll("_", " ")}: {t.status.replace("_", " ")}</Badge>)}</div>}
            {!!l.sources?.length && <p className="mt-1 text-xs text-slate-500">From: {l.sources.join(", ")}</p>}
          </li>
        ))}
        {pending && <li className="mr-10 text-xs text-slate-500">Agent is replying…</li>}
      </ol>
      <FormError message={error} />
      {ended ? <Button type="button" variant="secondary" onClick={begin}>Start a new chat</Button> : (
        <form onSubmit={send} className="flex gap-2">
          <Input aria-label="Your message" value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} placeholder="I'd like to book an appointment tomorrow, my name is Asha" />
          <Button type="submit" disabled={pending || !text.trim()}>Send</Button>
        </form>
      )}
      <p className="text-xs text-slate-500">Recorded under Calls as a chat. <a className="underline" href={`/app/calls/${callId}`}>Open the record</a></p>
    </div>
  );
}

export function SecretReveal({ state }: { state: ActionState }) {
  const secret = state?.data?.secret;
  if (!secret) return null;
  return (
    <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm">
      <p className="mb-1 font-medium">Signing secret</p>
      <code className="block break-all rounded bg-white px-2 py-1 text-xs">{secret}</code>
      <p className="mt-1 text-xs text-slate-600">Verify each request: HMAC-SHA256 of &quot;timestamp.body&quot; with this secret must equal v1 in the X-XploVoice-Signature header.</p>
    </div>
  );
}

/** The browser's offset from UTC in minutes (as Date.getTimezoneOffset reports it), so a date-time field means local time. */
export function TzOffset() {
  const [off, setOff] = useState(0);
  useEffect(() => setOff(new Date().getTimezoneOffset()), []);
  return <input type="hidden" name="tz_offset" value={off} />;
}

/** A form whose action returns a one-time signing secret (new webhook, rotated secret). */
export function SecretForm({ action, submit, children, variant, className }: {
  action: (prev: ActionState, form: FormData) => Promise<ActionState>; submit: string; children?: React.ReactNode;
  variant?: "primary" | "secondary" | "danger" | "ghost"; className?: string;
}) {
  return <ActionForm action={action} submit={submit} variant={variant} className={className} render={(s) => <SecretReveal state={s} />}>{children}</ActionForm>;
}
