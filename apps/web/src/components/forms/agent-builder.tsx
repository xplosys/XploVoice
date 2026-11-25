// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import { useRouter } from "next/navigation";
import { useState, useTransition, type ReactNode } from "react";
import { saveAgentAction } from "@/app/app/agents/actions";
import type { Agent, AgentConfig, Day } from "@/lib/api";
import { Button, FormError, Input, Label, Select } from "@/components/ui";
import { cn } from "@/lib/utils";

export type ModelOption = { id: string; label: string; voices: { id: string; name: string }[] };
export type ModelOptions = { llm: ModelOption[]; stt: ModelOption[]; tts: ModelOption[] };

const LANGS = [["en-IN", "English (India)"], ["hi-IN", "Hindi"], ["hi-Latn-IN", "Hinglish"], ["en-US", "English (US)"]];
export const TYPES: [string, string][] = [
  ["receptionist", "AI Receptionist"], ["customer_support", "Customer Support"], ["appointment_booking", "Appointment Booking"],
  ["lead_qualification", "Lead Qualification"], ["sales_assistant", "Sales Assistant"], ["faq_assistant", "FAQ Assistant"],
  ["service_booking", "Service Booking"], ["follow_up", "Follow-up Agent"],
  ["healthcare_admin", "Healthcare Administrative Assistant"], ["custom", "Custom Agent"],
];
const TONES = ["friendly", "professional", "warm", "calm", "energetic", "concise"];
const TOOLS: [string, string][] = [
  ["check_availability", "Check availability"], ["book_appointment", "Book appointments"],
  ["reschedule_appointment", "Reschedule appointments"], ["cancel_appointment", "Cancel appointments"],
  ["create_lead", "Create leads"], ["create_ticket", "Create support tickets"], ["lookup_order", "Look up orders"],
  ["send_sms_confirmation", "Send SMS confirmations"],
];
const DAYS: [Day, string][] = [["mon", "Mon"], ["tue", "Tue"], ["wed", "Wed"], ["thu", "Thu"], ["fri", "Fri"], ["sat", "Sat"], ["sun", "Sun"]];
const TIMEZONES = ["Asia/Kolkata", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "UTC"];

const SECTIONS = [
  ["basics", "Basics"], ["conversation", "Conversation"], ["voice", "Voice and AI"], ["handling", "Call handling"],
  ["hours", "Business hours"], ["escalation", "Escalation and transfer"], ["recording", "Recording and fallback"],
  ["knowledge", "Knowledge and tools"],
] as const;
type Section = (typeof SECTIONS)[number][0];

function Area(p: { id: string; value: string; onChange: (v: string) => void; rows?: number; max: number; disabled?: boolean }) {
  return <textarea id={p.id} rows={p.rows ?? 3} maxLength={p.max} value={p.value} disabled={p.disabled}
    onChange={(e) => p.onChange(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />;
}

function Field({ label, id, hint, children }: { label: string; id?: string; hint?: string; children: ReactNode }) {
  return <div><Label htmlFor={id}>{label}</Label>{children}{hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}</div>;
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /> {label}</label>;
}

function Later({ children }: { children: ReactNode }) {
  return <p className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">{children}</p>;
}

/** The agent builder: every MP section 9 setting. Saving writes a new immutable version (when something changed);
 * it never changes what live callers reach. That only happens when a version is published. */
export function AgentBuilder({ agent, models, canEdit }: { agent: Agent; models: ModelOptions; canEdit: boolean }) {
  const router = useRouter();
  const [name, setName] = useState(agent.name);
  const [description, setDescription] = useState(agent.description);
  const [note, setNote] = useState("");
  const [c, setC] = useState<AgentConfig>(agent.config);
  const [section, setSection] = useState<Section>("basics");
  const [msg, setMsg] = useState<{ ok?: string; error?: string }>({});
  const [pending, start] = useTransition();
  const ro = !canEdit;

  function set<K extends keyof AgentConfig>(k: K, v: AgentConfig[K]) { setC((x) => ({ ...x, [k]: v })); }
  function sub<K extends keyof AgentConfig>(k: K, patch: Partial<AgentConfig[K]>) {
    setC((x) => ({ ...x, [k]: { ...(x[k] as object), ...patch } }));
  }

  function save() {
    setMsg({});
    start(async () => {
      const r = await saveAgentAction(agent.id, { name, description, note, config: c });
      setMsg(r);
      if (r.agent) { setNote(""); router.refresh(); }
    });
  }

  const tts = models.tts.find((m) => m.id === c.ai.tts_model_id);
  const voices = tts?.voices ?? Array.from(new Map(models.tts.flatMap((m) => m.voices).map((v) => [v.id, v])).values());
  const bh = c.business_hours;

  return (
    <div className="grid gap-6 md:grid-cols-[11rem_1fr]">
      <nav aria-label="Builder sections" className="flex gap-1 overflow-x-auto md:flex-col">
        {SECTIONS.map(([k, label]) => (
          <button key={k} type="button" onClick={() => setSection(k)} aria-current={section === k}
            className={cn("whitespace-nowrap rounded-md px-3 py-2 text-left text-sm", section === k ? "bg-brand-50 font-medium text-brand-700" : "text-slate-700 hover:bg-slate-100")}>
            {label}
          </button>
        ))}
      </nav>
      <fieldset disabled={ro} className="min-w-0 space-y-4">
        {section === "basics" && (<>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Agent name" id="name" hint="The agent introduces itself by this name."><Input id="name" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Agent type" id="agent_type">
              <Select id="agent_type" value={c.agent_type} onChange={(e) => set("agent_type", e.target.value)}>
                {TYPES.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</Select></Field>
          </div>
          <Field label="Description" id="description" hint="For your team; callers never hear it."><Input id="description" maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
          <Field label="Business purpose" id="business_purpose" hint="What this agent is for, in a sentence or two. It is added to the agent's instructions.">
            <Area id="business_purpose" max={1000} value={c.business_purpose} onChange={(v) => set("business_purpose", v)} /></Field>
          {c.agent_type === "healthcare_admin" && <Later>Healthcare administrative agents always get administrative-only safety rules: no diagnosis, prescribing or triage. Use synthetic data only. Health information must not go to any provider without an approved BAA.</Later>}
        </>)}

        {section === "conversation" && (<>
          <Field label="System prompt" id="system_prompt" hint="Instructions the AI follows on every call.">
            <Area id="system_prompt" rows={8} max={8000} value={c.system_prompt} onChange={(v) => set("system_prompt", v)} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Personality" id="personality"><Input id="personality" maxLength={500} value={c.personality} onChange={(e) => set("personality", e.target.value)} /></Field>
            <Field label="Tone" id="tone"><Select id="tone" value={c.tone} onChange={(e) => set("tone", e.target.value)}>
              {TONES.map((t) => <option key={t} value={t}>{t[0].toUpperCase() + t.slice(1)}</option>)}</Select></Field>
          </div>
          <Field label="Greeting message" id="greeting" hint="The first thing callers hear. Leave empty to let the caller speak first.">
            <Input id="greeting" maxLength={500} value={c.greeting} onChange={(e) => set("greeting", e.target.value)} /></Field>
          <Field label="Language" id="language"><Select id="language" value={c.language} onChange={(e) => set("language", e.target.value as AgentConfig["language"])}>
            {LANGS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</Select></Field>
        </>)}

        {section === "voice" && (<>
          <p className="text-sm text-slate-600">Choose from the models in your AI routes. The chosen model is tried first, and calls still fail over to your other routes. Leave a choice on default to follow your route order.</p>
          {(["llm", "stt", "tts"] as const).map((k) => {
            const key = `${k}_model_id` as "llm_model_id" | "stt_model_id" | "tts_model_id";
            const label = { llm: "LLM provider and model", stt: "Speech-to-text provider", tts: "Text-to-speech provider" }[k];
            return (
              <Field key={k} label={label} id={key} hint={models[k].length ? undefined : "No models are routed yet. Set them up under AI providers."}>
                <Select id={key} value={c.ai[key] ?? ""} onChange={(e) => sub("ai", { [key]: e.target.value || null, ...(k === "tts" ? { voice: null } : {}) })}>
                  <option value="">Default (your route order)</option>
                  {models[k].map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                </Select></Field>
            );
          })}
          <Field label="Voice" id="voice" hint="Voices come from the text-to-speech model, so the voice provider is that model's provider.">
            <Select id="voice" value={c.ai.voice ?? ""} onChange={(e) => sub("ai", { voice: e.target.value || null })}>
              <option value="">Provider default</option>
              {voices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </Select></Field>
        </>)}

        {section === "handling" && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Maximum call duration (seconds)" id="max_call_seconds" hint="30 to 900. The platform limit also applies.">
              <Input id="max_call_seconds" type="number" min={30} max={900} value={c.limits.max_call_seconds} onChange={(e) => sub("limits", { max_call_seconds: Number(e.target.value) })} /></Field>
            <Field label="Silence timeout (seconds)" id="silence_timeout_seconds" hint="After this much silence the agent checks in, then ends the call.">
              <Input id="silence_timeout_seconds" type="number" min={5} max={60} value={c.limits.silence_timeout_seconds} onChange={(e) => sub("limits", { silence_timeout_seconds: Number(e.target.value) })} /></Field>
            <Field label="Pause that ends the caller's turn (ms)" id="endpoint_silence_ms">
              <Input id="endpoint_silence_ms" type="number" min={200} max={2000} value={c.interruption.endpoint_silence_ms} onChange={(e) => sub("interruption", { endpoint_silence_ms: Number(e.target.value) })} /></Field>
            <Field label="Speech needed to interrupt the agent (ms)" id="barge_in_min_ms">
              <Input id="barge_in_min_ms" type="number" min={100} max={1500} value={c.interruption.barge_in_min_ms} onChange={(e) => sub("interruption", { barge_in_min_ms: Number(e.target.value) })} /></Field>
            <div className="sm:col-span-2"><Check label="Callers can interrupt the agent" checked={c.interruption.interruptible} onChange={(v) => sub("interruption", { interruptible: v })} /></div>
          </div>
        )}

        {section === "hours" && (<>
          <Check label="Use business hours" checked={bh.enabled} onChange={(v) => sub("business_hours", { enabled: v })} />
          {bh.enabled && (<>
            <Field label="Time zone" id="tz"><Select id="tz" value={bh.timezone} onChange={(e) => sub("business_hours", { timezone: e.target.value })}>
              {Array.from(new Set([bh.timezone, ...TIMEZONES])).map((t) => <option key={t}>{t}</option>)}</Select></Field>
            <table className="w-full text-sm"><tbody>
              {DAYS.map(([d, label]) => {
                const w = bh.weekly[d] ?? [];
                const open = w.length > 0;
                const setDay = (wins: typeof w) => sub("business_hours", { weekly: { ...bh.weekly, [d]: wins } });
                return (
                  <tr key={d} className="border-b border-slate-100">
                    <td className="w-16 py-2 font-medium">{label}</td>
                    <td className="w-28"><Check label="Open" checked={open} onChange={(v) => setDay(v ? [{ start: "09:00", end: "18:00" }] : [])} /></td>
                    <td className="py-2">{open && w.map((win, i) => (
                      <span key={i} className="mr-3 inline-flex items-center gap-1">
                        <input aria-label={`${label} opens`} type="time" value={win.start} className="rounded border border-slate-300 px-1" onChange={(e) => setDay(w.map((x, j) => j === i ? { ...x, start: e.target.value } : x))} />
                        –<input aria-label={`${label} closes`} type="time" value={win.end} className="rounded border border-slate-300 px-1" onChange={(e) => setDay(w.map((x, j) => j === i ? { ...x, end: e.target.value } : x))} />
                      </span>))}
                      {open && w.length < 4 && <button type="button" className="text-xs text-brand-700 underline" onClick={() => setDay([...w, { start: "14:00", end: "18:00" }])}>Add a window</button>}
                      {w.length > 1 && <button type="button" className="ml-2 text-xs text-slate-600 underline" onClick={() => setDay(w.slice(0, -1))}>Remove last</button>}
                    </td>
                  </tr>
                );
              })}
            </tbody></table>
            <Field label="After hours" id="after_hours"><Select id="after_hours" value={bh.after_hours} onChange={(e) => sub("business_hours", { after_hours: e.target.value as "answer" | "closed_message" })}>
              <option value="closed_message">Play the closed message and end the call</option><option value="answer">Answer as usual</option></Select></Field>
            {bh.after_hours === "closed_message" && <Field label="Closed message" id="closed_message"><Area id="closed_message" max={500} value={bh.closed_message} onChange={(v) => sub("business_hours", { closed_message: v })} /></Field>}
            <p className="text-xs text-slate-500">The agent also knows these hours, so it can tell callers when you are open. Test calls can simulate after-hours at any time.</p>
          </>)}
        </>)}

        {section === "escalation" && (<>
          <Check label="Hand the call over when the caller asks for a person" checked={c.escalation.enabled} onChange={(v) => sub("escalation", { enabled: v })} />
          {c.escalation.enabled && (<div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2"><Field label="Phrases that trigger a hand-over" id="phrases" hint="One per line. Matched anywhere in what the caller says, ignoring case.">
              <Area id="phrases" max={1300} value={c.escalation.phrases.join("\n")} onChange={(v) => sub("escalation", { phrases: v.split("\n").map((p) => p.trim()).filter(Boolean) })} /></Field></div>
            <Field label="Hand over after this many turns not understood" id="max_unclear" hint="0 turns this off.">
              <Input id="max_unclear" type="number" min={0} max={10} value={c.escalation.max_unclear_turns} onChange={(e) => sub("escalation", { max_unclear_turns: Number(e.target.value) })} /></Field>
            <Field label="Hand-over action" id="esc_action"><Select id="esc_action" value={c.escalation.action} onChange={(e) => sub("escalation", { action: e.target.value as AgentConfig["escalation"]["action"] })}>
              <option value="take_message">Take a message</option><option value="transfer">Transfer the call</option><option value="end_call">End the call politely</option></Select></Field>
            <div className="sm:col-span-2"><Field label="What the agent says" id="esc_message"><Area id="esc_message" max={500} value={c.escalation.message} onChange={(v) => sub("escalation", { message: v })} /></Field></div>
          </div>)}
          <hr className="border-slate-200" />
          <Check label="Allow call transfer" checked={c.transfer.enabled} onChange={(v) => sub("transfer", { enabled: v })} />
          {c.transfer.enabled && (<>
            {c.transfer.targets.map((t, i) => (
              <div key={i} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                <Input aria-label="Label" placeholder="Front desk" value={t.label} onChange={(e) => sub("transfer", { targets: c.transfer.targets.map((x, j) => j === i ? { ...x, label: e.target.value } : x) })} />
                <Input aria-label="Number" placeholder="+919812345678" value={t.number} onChange={(e) => sub("transfer", { targets: c.transfer.targets.map((x, j) => j === i ? { ...x, number: e.target.value } : x) })} />
                <Button type="button" variant="ghost" onClick={() => sub("transfer", { targets: c.transfer.targets.filter((_, j) => j !== i) })}>Remove</Button>
              </div>))}
            {c.transfer.targets.length < 5 && <Button type="button" variant="secondary" onClick={() => sub("transfer", { targets: [...c.transfer.targets, { label: "", number: "" }] })}>Add a number</Button>}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Announcement before transferring" id="announce"><Input id="announce" maxLength={300} value={c.transfer.announce} onChange={(e) => sub("transfer", { announce: e.target.value })} /></Field>
              <Field label="Transfer type" id="mode"><Select id="mode" value={c.transfer.mode} onChange={(e) => sub("transfer", { mode: e.target.value as "warm" | "cold" })}>
                <option value="cold">Cold (connect directly)</option><option value="warm">Warm (introduce the caller first)</option></Select></Field>
            </div>
            <Later>Transfers to a phone number are carried out by telephony, which arrives in Phase 6. On a browser test call the agent says the announcement and ends the call, and the call shows that a transfer was requested.</Later>
          </>)}
        </>)}

        {section === "recording" && (<>
          <Field label="Recording policy" id="recording"><Select id="recording" value={c.recording.policy} onChange={(e) => sub("recording", { policy: e.target.value as AgentConfig["recording"]["policy"] })}>
            <option value="off">Don&apos;t record</option><option value="ask_consent">Ask the caller first</option><option value="record">Record (with notice)</option></Select></Field>
          {c.recording.policy !== "off" && <Field label="Consent or notice message" id="consent"><Area id="consent" max={300} value={c.recording.consent_message} onChange={(v) => sub("recording", { consent_message: v })} /></Field>}
          <Later>Awaiting Phase 6: recording, consent capture and storage arrive with telephony. The policy is saved with the version; calls are not recorded yet.</Later>
          <hr className="border-slate-200" />
          <Field label="If the AI providers fail, the agent says" id="pf"><Area id="pf" max={300} value={c.fallback.provider_failure_message} onChange={(v) => sub("fallback", { provider_failure_message: v })} /></Field>
          <Field label="When the agent didn't catch what was said" id="unclear"><Input id="unclear" maxLength={300} value={c.fallback.unclear_message} onChange={(e) => sub("fallback", { unclear_message: e.target.value })} /></Field>
          <Field label="Then" id="on_failure"><Select id="on_failure" value={c.fallback.on_failure} onChange={(e) => sub("fallback", { on_failure: e.target.value as "end_call" | "transfer" })}>
            <option value="end_call">End the call</option><option value="transfer">Transfer the call (Phase 6)</option></Select></Field>
        </>)}

        {section === "knowledge" && (<>
          <Field label="Knowledge base" id="kb"><p className="text-sm text-slate-600">{c.knowledge_base_ids.length ? `${c.knowledge_base_ids.length} attached` : "None attached."}</p></Field>
          <Later>Awaiting Phase 5: knowledge bases (upload, scanning and search) are built in Phase 5. You&apos;ll attach them here then.</Later>
          <Field label="Tool permissions" hint="Choose which business actions this agent may take.">
            <div className="grid gap-2 sm:grid-cols-2">
              {TOOLS.map(([k, label]) => <Check key={k} label={label} checked={c.tools.includes(k)}
                onChange={(v) => set("tools", v ? [...c.tools, k] : c.tools.filter((x) => x !== k))} />)}
            </div></Field>
          <Later>Awaiting Phase 5: permissions are saved with the version, but the tool gateway that runs them arrives in Phase 5. Until then the agent can&apos;t book, look up or create anything.</Later>
        </>)}

        {canEdit && (
          <div className="flex flex-wrap items-end gap-3 border-t border-slate-200 pt-4">
            <div className="min-w-60 flex-1"><Field label="What changed (optional)" id="note"><Input id="note" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Friendlier greeting" /></Field></div>
            <Button type="button" onClick={save} disabled={pending}>{pending ? "Saving…" : "Save new version"}</Button>
          </div>
        )}
        <FormError message={msg.error} />
        {msg.ok && <p role="status" className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{msg.ok}</p>}
      </fieldset>
    </div>
  );
}
