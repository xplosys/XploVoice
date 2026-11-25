// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Room, RoomEvent, Track, type RemoteTrack } from "livekit-client";
import { endCallAction, startCallAction } from "@/app/app/agents/actions";
import { Badge, Button, Card, FormError } from "@/components/ui";

type Line = { speaker: "caller" | "agent"; text: string; open: boolean };
type Phase = "idle" | "connecting" | "waiting" | "live" | "ended";

const STATE_LABEL: Record<string, string> = {
  listening: "Listening", thinking: "Thinking", speaking: "Speaking", connected: "Agent joined",
};

/** Browser test call. Joins the call's LiveKit room with the microphone; the voice worker joins the same room
 * and runs exactly the engine a phone call uses. Transcript lines arrive as data messages from the worker. */
export function TestCall({ agentId, agentName, versions, latest, hasHours }: {
  agentId: string; agentName: string; versions: { id: string; version: number }[]; latest: string; hasHours: boolean;
}) {
  const [versionId, setVersionId] = useState(latest);
  const [afterHours, setAfterHours] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [agentState, setAgentState] = useState<string>("");
  const [lines, setLines] = useState<Line[]>([]);
  const [error, setError] = useState<string>();
  const [callId, setCallId] = useState<string>();
  const [endReason, setEndReason] = useState<string>();
  const room = useRef<Room | null>(null);
  const audio = useRef<HTMLDivElement>(null);

  useEffect(() => () => { room.current?.disconnect(); }, []);

  function onData(payload: Uint8Array, topic?: string) {
    if (topic !== "xv") return;
    let ev: { type: string; speaker?: "caller" | "agent"; text?: string; state?: string; reason?: string };
    try { ev = JSON.parse(new TextDecoder().decode(payload)); } catch { return; }
    if (ev.type === "state" && ev.state) {
      setAgentState(ev.state);
      if (ev.state === "connected") setPhase("live");
      if (ev.state !== "speaking") setLines((ls) => ls.map((l) => ({ ...l, open: false })));
    } else if (ev.type === "transcript" && ev.speaker && ev.text) {
      const { speaker, text } = ev;
      setLines((ls) => {
        const last = ls[ls.length - 1];
        if (speaker === "agent" && last?.speaker === "agent" && last.open) {
          return [...ls.slice(0, -1), { ...last, text: `${last.text} ${text}` }];
        }
        return [...ls.map((l) => ({ ...l, open: false })), { speaker, text, open: speaker === "agent" }];
      });
    } else if (ev.type === "ended") {
      setEndReason(ev.reason);
      setPhase("ended");
      room.current?.disconnect();
    }
  }

  async function start() {
    setError(undefined); setLines([]); setEndReason(undefined); setPhase("connecting");
    const r = await startCallAction(agentId, { versionId, afterHours });
    if (!r.session) { setError(r.error); setPhase("idle"); return; }
    setCallId(r.session.call_id);
    const rm = new Room({ adaptiveStream: true, dynacast: true });
    room.current = rm;
    rm.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
      if (track.kind === Track.Kind.Audio && audio.current) audio.current.appendChild(track.attach());
    });
    rm.on(RoomEvent.DataReceived, (payload, _p, _k, topic) => onData(payload, topic));
    rm.on(RoomEvent.Disconnected, () => setPhase((p) => (p === "idle" ? p : "ended")));
    try {
      await rm.connect(r.session.livekit_url, r.session.token);
      await rm.startAudio();
      await rm.localParticipant.setMicrophoneEnabled(true);
      setPhase((p) => (p === "connecting" ? "waiting" : p));
    } catch {
      setError("Could not connect the call. Check that your browser can use the microphone and that the voice service is running.");
      await endCallAction(r.session.call_id);
      rm.disconnect();
      setPhase("idle");
    }
  }

  async function hangUp() {
    if (callId) await endCallAction(callId);
    room.current?.disconnect();
    setPhase("ended");
  }

  const live = phase === "connecting" || phase === "waiting" || phase === "live";
  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-medium">Test call with {agentName}</h2>
          <p className="text-sm text-slate-600">Speak through your microphone. You can interrupt the agent at any time.</p>
        </div>
        <div className="flex items-center gap-2">
          {phase === "waiting" && <Badge tone="amber">Waiting for the agent…</Badge>}
          {phase === "live" && agentState && <Badge tone={agentState === "speaking" ? "brand" : "green"}>{STATE_LABEL[agentState] ?? agentState}</Badge>}
          {phase === "ended" && <Badge>Call ended{endReason ? `: ${endReason.replaceAll("_", " ")}` : ""}</Badge>}
          {live
            ? <Button variant="secondary" className="text-red-700" onClick={hangUp}>End call</Button>
            : <Button onClick={start}>{phase === "ended" ? "Call again" : "Start call"}</Button>}
        </div>
      </div>
      {!live && (
        <div className="mb-4 flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2">Version
            <select value={versionId} onChange={(e) => setVersionId(e.target.value)} className="rounded-md border border-slate-300 px-2 py-1">
              {versions.map((v) => <option key={v.id} value={v.id}>Version {v.version}{v.id === latest ? " (latest)" : ""}</option>)}
            </select></label>
          {hasHours && <label className="flex items-center gap-2"><input type="checkbox" checked={afterHours} onChange={(e) => setAfterHours(e.target.checked)} /> Simulate after hours</label>}
        </div>
      )}
      <FormError message={error} />
      <div aria-live="polite" className="min-h-40 space-y-2 rounded-md bg-slate-50 p-3 text-sm">
        {lines.length === 0 && <p className="text-slate-500">{live ? "The conversation will appear here." : "No call yet."}</p>}
        {lines.map((l, i) => (
          <p key={i} className={l.speaker === "agent" ? "text-slate-900" : "text-brand-700"}>
            <span className="font-medium">{l.speaker === "agent" ? agentName : "You"}:</span> {l.text}
          </p>
        ))}
      </div>
      {phase === "ended" && callId && (
        <p className="mt-3 text-sm"><Link className="text-brand-700 underline" href={`/app/calls/${callId}`}>See the transcript and timings</Link></p>
      )}
      <div ref={audio} className="hidden" />
    </Card>
  );
}
