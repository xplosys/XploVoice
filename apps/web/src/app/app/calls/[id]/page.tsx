// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { api, ApiError, type CallDetail } from "@/lib/api";
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
  const providers = Object.assign({}, ...turns.map((t) => t.providers ?? {})) as Record<string, string>;
  const notable = call.events.filter((e) => !["turn.metrics", "state.changed"].includes(e.type));
  return (
    <div className="space-y-6">
      <div>
        <Link href="/app/calls" className="text-sm text-brand-700 underline">Calls</Link>
        <h1 className="text-2xl font-semibold">{call.agent_name} <span className="text-base font-normal text-slate-500">version {call.agent_version}</span></h1>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <Badge tone={callTone(call.status)}>{call.status}</Badge>
          {call.end_reason && <span>Ended: {call.end_reason.replace("_", " ")}</span>}
          <span>· {new Date(call.created_at).toLocaleString()}</span>
          {call.duration_seconds && <span>· {Number(call.duration_seconds).toFixed(1)} s</span>}
          {call.recoveries > 0 && <Badge tone="amber">recovered {call.recoveries}×</Badge>}
        </p>
      </div>
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
      <Card className="overflow-x-auto p-0">
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
      </Card>
      <Card>
        <h2 className="mb-2 font-medium">Providers used</h2>
        {Object.keys(providers).length === 0 ? <p className="text-sm text-slate-600">None.</p> : (
          <ul className="text-sm">{Object.entries(providers).map(([k, v]) => <li key={k}><span className="uppercase text-slate-500">{k}</span> · {v}</li>)}</ul>
        )}
        {notable.length > 0 && (
          <>
            <h3 className="mb-1 mt-4 text-sm font-medium">Events</h3>
            <ul className="text-xs text-slate-600">{notable.map((e, i) => <li key={i}>{new Date(e.occurred_at).toLocaleTimeString()} · {e.type.replace(".", " ")}</li>)}</ul>
          </>
        )}
      </Card>
    </div>
  );
}
