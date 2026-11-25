// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { api, ApiError, type Appointment, type CallDetail, type Lead, type Ticket, type ToolExecution } from "@/lib/api";
import { EXEC_TONE, label } from "@/lib/tones";
import { can, getMe } from "@/lib/me";
import { Badge, Card } from "@/components/ui";
import { callTone } from "@/lib/utils";

export const metadata = { title: "Call · XploVoice" };

type Metrics = { turn: number; kind: string; interrupted?: boolean; endpoint_ms?: number; stt_ms?: number;
  llm_first_token_ms?: number; tts_first_audio_ms?: number; first_audible_ms?: number; providers?: Record<string, string> };
const ms = (v?: number) => (v == null ? "–" : `${v}`);

export default async function CallPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await getMe();
  if (!can(me, "calls:read")) redirect("/app");
  const { id } = await params;
  const call = await api<CallDetail>(`/v1/calls/${encodeURIComponent(id)}`).catch((e) => {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  });
  const turns = call.events.filter((e) => e.type === "turn.metrics").map((e) => e.data as Metrics);
  const q = `call_id=${encodeURIComponent(call.id)}`;
  const none = <T,>() => Promise.resolve([] as T[]);
  const [execs, appts, leads, tickets] = await Promise.all([
    api<ToolExecution[]>(`/v1/tools/executions?${q}`).catch(() => [] as ToolExecution[]),
    can(me, "workflows:read") ? api<Appointment[]>(`/v1/appointments?${q}`).catch(() => [] as Appointment[]) : none<Appointment>(),
    can(me, "workflows:read") ? api<Lead[]>(`/v1/leads?${q}`).catch(() => [] as Lead[]) : none<Lead>(),
    can(me, "support:read") ? api<Ticket[]>(`/v1/tickets?${q}`).catch(() => [] as Ticket[]) : none<Ticket>(),
  ]);
  const retrieved = call.events.filter((e) => e.type === "kb.retrieved").length;
  const notable = call.events.filter((e) => !["turn.metrics", "state.changed"].includes(e.type));
  return (
    <div className="space-y-6">
      <div>
        <Link href="/app/calls" className="text-sm text-brand-700 underline">Calls</Link>
        <h1 className="text-2xl font-semibold">{call.agent_name} <Link href={`/app/agents/${call.agent_id}/versions/${call.agent_version}`} className="text-base font-normal text-slate-500 underline">version {call.agent_version}</Link></h1>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <Badge tone={callTone(call.status)}>{call.status}</Badge>
          {call.end_reason && <span>Ended: {call.end_reason.replaceAll("_", " ")}</span>}
          <span>· {new Date(call.created_at).toLocaleString()}</span>
          {call.duration_seconds && <span>· {Number(call.duration_seconds).toFixed(1)} s</span>}
          {call.recoveries > 0 && <Badge tone="amber">recovered {call.recoveries}×</Badge>}
        </p>
      </div>
      {Object.keys(call.providers_used).length > 0 && (
        <Card>
          <h2 className="mb-2 font-medium">Providers and models used</h2>
          <ul className="grid gap-1 text-sm sm:grid-cols-3">
            {(["stt", "llm", "tts"] as const).map((k) => {
              const u = call.providers_used[k];
              return u ? <li key={k}><span className="font-medium">{{ stt: "Speech-to-text", llm: "Language model", tts: "Text-to-speech" }[k]}:</span> {u.provider}, {u.model} <span className="font-mono text-xs text-slate-500">({u.model_version}, {u.account === "customer" ? "your key" : "XploVoice account"})</span></li> : null;
            })}
          </ul>
        </Card>
      )}
      <Card>
        <h2 className="mb-3 font-medium">Transcript</h2>
        {call.transcript.length === 0 ? <p className="text-sm text-slate-600">Nothing was said on this call.</p> : (
          <div className="space-y-2 text-sm">
            {call.transcript.map((s) => (
              <p key={s.seq} className={s.speaker === "agent" ? "" : "text-brand-700"}>
                <span className="font-medium">{s.speaker === "agent" ? call.agent_name : "Caller"}:</span> {s.text}
                {s.interrupted && <span className="ml-2 text-xs text-amber-700">(interrupted)</span>}
              </p>
            ))}
          </div>
        )}
      </Card>
      {(execs.length > 0 || appts.length + leads.length + tickets.length > 0 || retrieved > 0) && (
        <Card>
          <h2 className="mb-2 font-medium">Actions on this call</h2>
          {retrieved > 0 && <p className="mb-2 text-sm text-slate-600">The agent looked up its knowledge base on {retrieved} turn{retrieved === 1 ? "" : "s"}.</p>}
          {execs.length > 0 && <ul className="mb-3 space-y-1 text-sm">{execs.map((e) => (
            <li key={e.id}>{new Date(e.created_at).toLocaleTimeString()} · {e.label} <Badge tone={EXEC_TONE[e.status] ?? "slate"}>{label(e.status)}</Badge>{e.error && <span className="text-xs text-slate-500"> · {e.error}</span>}</li>))}</ul>}
          <ul className="space-y-1 text-sm">
            {appts.map((a) => <li key={a.id}>Appointment <span className="font-mono text-xs">{a.reference}</span> · {a.local_start.replace("T", " ")} · {a.customer_name} · <Link className="underline" href="/app/appointments">{a.status}</Link></li>)}
            {leads.map((l) => <li key={l.id}>Lead <Link className="underline" href={`/app/leads/${l.id}`}>{l.name}</Link> · {l.status}</li>)}
            {tickets.map((t) => <li key={t.id}>Ticket <Link className="underline" href={`/app/tickets/${t.id}`}>{t.reference}</Link> · {t.subject} · {t.status}</li>)}
          </ul>
        </Card>
      )}
      {turns.length > 0 && <Card className="overflow-x-auto p-0">
        <h2 className="px-6 pt-5 font-medium">Response timing (ms)</h2>
        <p className="px-6 text-xs text-slate-500">First audible response is measured from the moment the caller stopped speaking, including the pause the agent waits for.</p>
        <table className="mt-3 w-full text-left text-sm">
          <thead className="border-y border-slate-200 text-slate-500"><tr>
            <th className="px-6 py-2 font-medium">Turn</th><th className="px-4 py-2 text-right font-medium">End of turn</th>
            <th className="px-4 py-2 text-right font-medium">Speech-to-text</th><th className="px-4 py-2 text-right font-medium">LLM first token</th>
            <th className="px-4 py-2 text-right font-medium">Text-to-speech</th><th className="px-4 py-2 text-right font-medium">First audible</th></tr></thead>
          <tbody>
            {turns.map((t) => (
              <tr key={t.turn} className="border-b border-slate-100 last:border-0">
                <td className="px-6 py-2">{t.turn} · {t.kind}{t.interrupted && <span className="ml-1 text-xs text-amber-700">interrupted</span>}</td>
                <td className="px-4 py-2 text-right">{ms(t.endpoint_ms)}</td><td className="px-4 py-2 text-right">{ms(t.stt_ms)}</td>
                <td className="px-4 py-2 text-right">{ms(t.llm_first_token_ms)}</td><td className="px-4 py-2 text-right">{ms(t.tts_first_audio_ms)}</td>
                <td className="px-4 py-2 text-right font-medium">{ms(t.first_audible_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>}
      <Card>
        <h2 className="mb-2 font-medium">Events</h2>
        {notable.length === 0 ? <p className="text-sm text-slate-600">None.</p> : (
          <ul className="text-xs text-slate-600">{notable.map((e, i) => <li key={i}>{new Date(e.occurred_at).toLocaleTimeString()} · {e.type.replaceAll(".", " ").replaceAll("_", " ")}{typeof e.data?.trigger === "string" ? ` (${e.data.trigger})` : ""}</li>)}</ul>
        )}
      </Card>
    </div>
  );
}
