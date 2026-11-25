// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import { useActionState } from "react";
import { saveAgentAction } from "@/app/app/agents/actions";
import type { Agent } from "@/lib/api";
import { Button, FormError, Input, Label, Select } from "@/components/ui";

const LANGS = [["en-IN", "English (India)"], ["hi-IN", "Hindi"], ["hi-Latn-IN", "Hinglish"], ["en-US", "English (US)"]];

export function AgentForm({ agent, canEdit }: { agent?: Agent; canEdit: boolean }) {
  const [state, action, pending] = useActionState(saveAgentAction, undefined);
  const c = agent?.config;
  return (
    <form action={action} className="space-y-4">
      {agent && <input type="hidden" name="id" value={agent.id} />}
      <fieldset disabled={!canEdit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div><Label htmlFor="name">Name</Label><Input id="name" name="name" required maxLength={120} defaultValue={agent?.name ?? "Front desk"} /></div>
          <div><Label htmlFor="language">Language</Label>
            <Select id="language" name="language" defaultValue={c?.language ?? "en-IN"}>
              {LANGS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</Select></div>
        </div>
        <div><Label htmlFor="greeting">Greeting</Label>
          <Input id="greeting" name="greeting" maxLength={500} defaultValue={c?.greeting ?? "Hello, thanks for calling. How can I help you today?"} /></div>
        <div><Label htmlFor="instructions">Instructions</Label>
          <textarea id="instructions" name="instructions" rows={5} maxLength={8000} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            defaultValue={c?.instructions ?? "You are the receptionist for a dental clinic. Help callers book, move or cancel appointments. Keep replies short."} /></div>
        <details className="rounded-md border border-slate-200 p-3 text-sm">
          <summary className="cursor-pointer font-medium">Conversation timing</summary>
          <div className="mt-3 grid gap-4 sm:grid-cols-3">
            <div><Label htmlFor="endpoint_silence_ms">Pause that ends the caller&apos;s turn (ms)</Label>
              <Input id="endpoint_silence_ms" name="endpoint_silence_ms" type="number" min={200} max={2000} defaultValue={c?.endpoint_silence_ms ?? 600} /></div>
            <div><Label htmlFor="barge_in_min_ms">Speech needed to interrupt the agent (ms)</Label>
              <Input id="barge_in_min_ms" name="barge_in_min_ms" type="number" min={100} max={1500} defaultValue={c?.barge_in_min_ms ?? 250} /></div>
            <div><Label htmlFor="silence_timeout_seconds">Silence before checking in (s)</Label>
              <Input id="silence_timeout_seconds" name="silence_timeout_seconds" type="number" min={5} max={60} defaultValue={c?.silence_timeout_seconds ?? 15} /></div>
            <div><Label htmlFor="max_call_seconds">Maximum call length (s)</Label>
              <Input id="max_call_seconds" name="max_call_seconds" type="number" min={30} max={900} defaultValue={c?.max_call_seconds ?? 300} /></div>
            <div><Label htmlFor="voice">Voice id (optional)</Label><Input id="voice" name="voice" maxLength={80} defaultValue={c?.voice ?? ""} /></div>
            <label className="flex items-center gap-2 self-end pb-2"><input type="checkbox" name="interruptible" defaultChecked={c?.interruptible ?? true} /> Callers can interrupt</label>
          </div>
        </details>
      </fieldset>
      <FormError message={state?.error} />
      {state?.ok && <p role="status" className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{state.ok}</p>}
      {canEdit && <Button type="submit" disabled={pending}>{pending ? "Saving…" : agent ? "Save new version" : "Create agent"}</Button>}
    </form>
  );
}
