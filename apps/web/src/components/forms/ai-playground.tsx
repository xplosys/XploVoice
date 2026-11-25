// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import { useActionState } from "react";
import { testChatAction, testSpeechAction, testTranscribeAction, type TestState } from "@/app/app/ai/actions";
import { fmtQty } from "@/lib/utils";
import { Button, Card, FormError, Input, Label, Select } from "@/components/ui";

const LANGS = [["", "Any"], ["en-IN", "English (India)"], ["hi-IN", "Hindi"], ["hi-Latn-IN", "Hinglish"], ["en-US", "English (US)"]];

function Lang() {
  return (
    <div><Label>Language</Label>
      <Select name="language" defaultValue="">{LANGS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</Select></div>
  );
}

function Result({ s }: { s: TestState }) {
  const r = s?.result ?? s?.detail;
  return (
    <>
      <FormError message={s?.error} />
      {s?.result?.text && <p className="whitespace-pre-wrap rounded-md bg-slate-50 p-3 text-sm">{s.result.text}</p>}
      {s?.result?.audio_base64 && (
        <audio controls className="w-full" src={`data:${s.result.mime};base64,${s.result.audio_base64}`} />
      )}
      {r && (
        <div className="space-y-1 text-xs text-slate-600">
          {s?.result && <p>Served by <b>{r.provider} · {r.model}</b> ({r.account === "customer" ? "your key" : "XploVoice account"}). Metered: {Object.entries(r.units).map(([u, q]) => fmtQty(q, u)).join(", ")}</p>}
          {r.attempts?.map((a, i) => <p key={i}>Attempt {i + 1}: {a.provider} · {a.model}: {a.outcome}{a.error ? ` (${a.error})` : ""}{a.latency_ms != null ? ` in ${a.latency_ms} ms` : ""}</p>)}
          {r.skipped?.map((k, i) => <p key={i}>Skipped {k.provider} · {k.model}: {k.reason}</p>)}
        </div>
      )}
    </>
  );
}

export function Playground() {
  const [chat, chatAction, chatPending] = useActionState(testChatAction, undefined);
  const [speech, speechAction, speechPending] = useActionState(testSpeechAction, undefined);
  const [stt, sttAction, sttPending] = useActionState(testTranscribeAction, undefined);
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="lg:col-span-2">
        <h2 className="mb-3 font-medium">Language model</h2>
        <form action={chatAction} className="space-y-3">
          <div><Label htmlFor="prompt">Message</Label>
            <textarea id="prompt" name="prompt" required maxLength={2000} rows={3} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              defaultValue="A patient wants to move their cleaning appointment to Friday morning. Reply in one sentence." /></div>
          <div className="grid gap-3 sm:grid-cols-2"><Lang />
            <div><Label htmlFor="system">Instructions (optional)</Label><Input id="system" name="system" maxLength={2000} placeholder="You are a friendly receptionist." /></div></div>
          <Result s={chat} />
          <Button type="submit" disabled={chatPending}>{chatPending ? "Running…" : "Send"}</Button>
        </form>
      </Card>
      <Card>
        <h2 className="mb-3 font-medium">Text-to-speech</h2>
        <form action={speechAction} className="space-y-3">
          <div><Label htmlFor="text">Text</Label><Input id="text" name="text" required maxLength={500} defaultValue="Your appointment is confirmed for Friday at ten." /></div>
          <div className="grid gap-3 sm:grid-cols-2"><Lang />
            <div><Label htmlFor="voice">Voice (optional)</Label><Input id="voice" name="voice" maxLength={80} /></div></div>
          <Result s={speech} />
          <Button type="submit" disabled={speechPending}>{speechPending ? "Running…" : "Speak"}</Button>
        </form>
      </Card>
      <Card>
        <h2 className="mb-3 font-medium">Speech-to-text</h2>
        <form action={sttAction} className="space-y-3">
          <div><Label htmlFor="audio">Audio file (WAV recommended, up to 5 MB)</Label>
            <input id="audio" name="audio" type="file" accept="audio/*" required className="block w-full text-sm" /></div>
          <Lang />
          <Result s={stt} />
          <Button type="submit" disabled={sttPending}>{sttPending ? "Running…" : "Transcribe"}</Button>
        </form>
      </Card>
    </div>
  );
}
