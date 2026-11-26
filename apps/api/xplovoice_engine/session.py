# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""One live call: turn-taking, the STT -> LLM -> TTS pipeline, barge-in, guards and per-stage timing.

Rules from the design (Phase 0 report, sections E and G):
- Only text the caller actually heard enters history. On barge-in the rest of the reply is dropped.
- The reply streams: text-to-speech starts on the first clause while the model is still writing.
- Each stage is timed; every turn's timings are stored with the call and exported as metrics.
- If no provider can serve a stage, the caller hears a fixed message and the call ends cleanly.
"""

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from prometheus_client import Counter, Histogram

from .audio import FRAME_MS, from_wav, to_wav
from .audio import frames as split_frames
from .backend import Bootstrap, CallEndedError, NoProviderError
from .channel import Channel
from .clauses import ClauseSplitter
from .turns import EnergyVad, TurnDetector, Utterance, Vad

log = logging.getLogger("xplovoice.engine")

STAGE = Histogram(
    "xv_voice_stage_seconds",
    "Voice pipeline stage latency",
    ["stage"],
    buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0),
)
EVENTS = Counter("xv_voice_events_total", "Voice engine events", ["event"])

LANGUAGE_NAMES = {"en-IN": "Indian English", "hi-IN": "Hindi", "hi-Latn-IN": "Hinglish", "en-US": "US English"}
MESSAGES = {
    "unavailable": "Sorry, I'm having trouble right now and can't continue this call. Please try again later.",
    "still_there": "Are you still there?",
    "silence_bye": "I haven't heard anything for a while, so I'll end the call now. Goodbye.",
    "time_limit": "We've reached the time limit for this call. Thank you, goodbye.",
    "resumed": "Sorry about that, I'm back. Please go on.",
    "opted_out": "Understood. We won't call you again. Goodbye.",
    "transfer_failed": "Sorry, I couldn't connect you. I'll pass your message to the team so they can call you back.",
}
DECLINE_WORDS = frozenset({"no", "nope", "don't", "dont", "not", "nahi", "nahin", "mat"})
KEYPAD_PAUSE_S = 2.0


@dataclass
class TurnMetrics:
    turn: int
    kind: str  # greeting | reply | system
    stt_ms: int | None = None
    llm_first_token_ms: int | None = None
    llm_total_ms: int | None = None
    tts_first_audio_ms: int | None = None
    first_audible_ms: int | None = None
    response_complete_ms: int | None = None
    endpoint_ms: int | None = None
    interrupted: bool = False
    providers: dict[str, str] = field(default_factory=dict)
    tools: list[str] | None = None  # business tools that ran during this reply

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class CallSession:
    def __init__(
        self,
        backend: Any,
        channel: Channel,
        boot: Bootstrap,
        *,
        worker_id: str,
        vad: Vad | None = None,
        clock: Any = time.monotonic,
    ) -> None:
        self.backend = backend
        self.channel = channel
        self.boot = boot
        self.cfg = boot.config
        self.speed = float(getattr(channel, "speed", 1.0))
        self.clock = clock
        self.lang: str | None = self.cfg.get("language")
        self.voice: str | None = self.cfg.get("voice")
        self.turns = TurnDetector(vad or EnergyVad(), int(self.cfg.get("endpoint_silence_ms", 600)))
        self.barge_in_ms = int(self.cfg.get("barge_in_min_ms", 250))
        self.interruptible = bool(self.cfg.get("interruptible", True))
        self.silence_limit_ms = int(self.cfg.get("silence_timeout_seconds", 15)) * 1000
        self.msg = MESSAGES | {k: v for k, v in (self.cfg.get("messages") or {}).items() if v}
        self.escalation: dict[str, Any] = self.cfg.get("escalation") or {"enabled": False}
        self.unclear_turns = 0
        # Phase 6: phone calls (transfer, opt-out, recording consent, keypad)
        self.tel: dict[str, Any] = self.cfg.get("telephony") or {}
        self.opt_out_phrases: list[str] = list(self.tel.get("opt_out_phrases") or [])
        self.recording: dict[str, Any] = self.tel.get("recording") or {"policy": "off"}
        self.consent_pending = False
        self.keys = ""
        self.rid = f"{worker_id[:12]}-{uuid.uuid4().hex[:8]}"
        self.seq = boot.next_seq
        self.turn_no = 0
        self.state = "listening"
        self.respond_task: asyncio.Task | None = None
        self.ended = asyncio.Event()
        self.end_reason = "caller_hangup"
        self.end_status = "completed"
        self.silent_ms = 0
        self.prompted = False
        self.closing = False
        self.event_no = 0
        self.events: list[dict] = []
        self.segments: list[dict] = []
        self.messages: list[dict[str, str]] = [{"role": "system", "content": self._system_prompt()}]
        for h in boot.history:
            self.messages.append({"role": "user" if h["speaker"] == "caller" else "assistant", "content": h["text"]})
        self.metrics: list[TurnMetrics] = []

    # ------------------------------------------------------------------ setup
    def _system_prompt(self) -> str:
        lang = LANGUAGE_NAMES.get(self.lang or "", "the caller's language")
        return (
            f"{self.cfg.get('instructions', '')}\n\nYou are speaking on a live voice call. Reply in {lang}. Keep "
            "replies short and natural to say aloud: no lists, markdown, emoji or URLs."
        )

    def _req(self, kind: str) -> str:
        return f"{self.rid}-{self.turn_no}-{kind}-{uuid.uuid4().hex[:6]}"

    def _wall_ms(self, since: float) -> int:
        return int((self.clock() - since) * 1000)

    # ------------------------------------------------------------------ main loop
    async def run(self) -> str:
        await self.backend.set_state("active")
        await self.channel.send({"type": "state", "state": "connected", "agent": self.boot.agent_name})
        listener = asyncio.create_task(self._listen())
        remaining = max(1.0, float(self.cfg.get("max_call_seconds", 300)) - self.boot.elapsed_seconds)
        limiter = asyncio.create_task(self._deadline(remaining))
        opening = self.msg["resumed"] if self.boot.resumed else self.cfg.get("greeting")
        keypad = asyncio.create_task(self._keypad()) if getattr(self.channel, "dtmf", None) is not None else None
        if not self.boot.resumed and self.recording.get("policy") in ("record", "ask_consent"):
            notice = self.recording.get("consent_message") or ""
            opening = f"{notice} {opening or ''}".strip()
            self.consent_pending = self.recording.get("policy") == "ask_consent"
            self._event("recording.notice", {"policy": self.recording.get("policy")})
        if self.tel.get("fallback_message") and not self.boot.resumed:
            self._event("fallback", {})
            self._start(self._final_words(self.tel["fallback_message"], "unavailable"))
        elif self.cfg.get("closed") and not self.boot.resumed:
            self._event("after_hours", {})
            self._start(self._final_words(self.cfg["closed"], "after_hours"))
        elif opening and self.recording.get("policy") in ("record", "ask_consent") and not self.boot.resumed:
            self._start(self._uninterrupted(opening))  # the caller must hear the whole recording notice
        elif opening:
            self._start(self._respond(None, preset=opening, kind="greeting" if not self.boot.resumed else "system"))
        done_wait = asyncio.create_task(self.ended.wait())
        await asyncio.wait({listener, done_wait}, return_when=asyncio.FIRST_COMPLETED)
        if listener.done() and not self.ended.is_set():
            self.end_reason = "caller_hangup"
        for t in (listener, limiter, done_wait, keypad, self.respond_task):
            if t and not t.done():
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
        await self._flush(final=True)
        with contextlib.suppress(Exception):
            await self.backend.set_state(self.end_status, self.end_reason)
        with contextlib.suppress(Exception):
            await self.channel.send({"type": "ended", "reason": self.end_reason})
        with contextlib.suppress(Exception):
            await self.channel.close()
        EVENTS.labels(f"ended:{self.end_reason}").inc()
        return self.end_reason

    def end(self, reason: str, status: str = "completed") -> None:
        if not self.ended.is_set():
            self.end_reason, self.end_status = reason, status
            self.ended.set()

    def _start(self, coro: Any) -> None:
        self.respond_task = asyncio.create_task(coro)

    @property
    def responding(self) -> bool:
        return self.respond_task is not None and not self.respond_task.done()

    async def _deadline(self, seconds: float) -> None:
        await asyncio.sleep(seconds / self.speed)
        await self._final_words(self.msg["time_limit"], "max_duration")

    async def _final_words(self, text: str, reason: str, status: str = "completed") -> None:
        """Interrupts whatever is happening, says a closing line that cannot be interrupted, then ends."""
        if self.closing:
            return
        self.closing = True
        if self.responding and self.respond_task is not asyncio.current_task():
            self.respond_task.cancel()  # type: ignore[union-attr]
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.respond_task  # type: ignore[misc]
        self.interruptible = False
        with contextlib.suppress(NoProviderError, CallEndedError, Exception):
            await self._respond(None, preset=text, kind="system")
        self._event("guard", {"reason": reason})
        self.end(reason, status)

    # ------------------------------------------------------------------ listening and barge-in
    async def _listen(self) -> None:
        async for frame in self.channel.frames():
            if self.ended.is_set():
                return
            if self.closing or (self.state == "speaking" and not self.interruptible):
                self.turns.reset()
                continue
            started, utt = self.turns.feed(frame)
            if started:
                self.silent_ms, self.prompted = 0, False
            if self.responding and self.interruptible and self.turns.speech_ms >= self.barge_in_ms:
                await self._barge_in()
            if utt is not None:
                if self.responding:
                    continue  # a short backchannel ("uh-huh") under the barge-in threshold: keep talking
                lag_ms = self.turns.clock_ms - utt.end_ms
                speech_end = self.clock() - lag_ms / 1000 / self.speed
                self._start(self._respond(utt, speech_end=speech_end, endpoint_ms=lag_ms))
                continue
            if not self.responding and not self.turns.speaking:
                self.silent_ms += FRAME_MS
                if self.silent_ms >= self.silence_limit_ms:
                    self.silent_ms = 0
                    if not self.prompted:
                        self.prompted = True
                        self._start(self._respond(None, preset=self.msg["still_there"], kind="system"))
                    else:
                        self._start(self._final_words(self.msg["silence_bye"], "silence_timeout"))

    async def _barge_in(self) -> None:
        task = self.respond_task
        if task is None:
            return
        task.cancel()
        await self.channel.clear_output()  # silence the agent first; bookkeeping can follow
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        EVENTS.labels("barge_in").inc()
        self._event("barge_in", {"turn": self.turn_no})
        self._set_state("listening")

    def _set_state(self, state: str) -> None:
        self.state = state
        asyncio.get_running_loop().create_task(self.channel.send({"type": "state", "state": state}))

    # ------------------------------------------------------------------ one response
    async def _respond(
        self,
        utt: Utterance | None,
        *,
        preset: str | None = None,
        kind: str = "reply",
        speech_end: float | None = None,
        endpoint_ms: int | None = None,
        typed: str | None = None,
    ) -> None:
        self.turn_no += 1
        m = TurnMetrics(turn=self.turn_no, kind=kind, endpoint_ms=endpoint_ms)
        t0 = speech_end if speech_end is not None else self.clock()
        spoken: list[str] = []
        progress = {"clause": "", "played": 0, "total": 0}
        self._set_state("thinking")
        try:
            if utt is not None or typed is not None:
                if typed is not None:
                    text = typed
                    self._segment("caller", f"[keypad] {typed}")
                    self.messages.append(
                        {"role": "user", "content": f"(The caller pressed keys on the keypad: {typed})"}
                    )
                else:
                    text = await self._transcribe(utt, m)  # type: ignore[arg-type]
                if text and self._opted_out(text):
                    return
                if text and self.consent_pending:
                    self._consent_answer(text)
                trigger = self._escalation_trigger(text)
                if trigger:
                    self._escalate(trigger)
                    return
                source: AsyncIterator[str] = self._llm_clauses(m) if text else self._preset_clauses(self.msg["unclear"])
            else:
                source = self._preset_clauses(preset or "")
            await self._speak(source, m, t0, spoken, progress)
            m.response_complete_ms = self._wall_ms(t0)
        except asyncio.CancelledError:
            m.interrupted = True
            raise
        except NoProviderError as e:
            log.warning("call %s: no provider (%s)", self.boot.call_id, e)
            self._event("no_provider", {"turn": self.turn_no})
            if kind != "system":
                asyncio.get_running_loop().create_task(
                    self._final_words(self.msg["unavailable"], "no_provider", "failed")
                )
            else:
                self.end("no_provider", "failed")
        except CallEndedError:
            self.end("user_ended")
        finally:
            if progress["clause"] and progress["total"]:
                words = progress["clause"].split()
                k = int(len(words) * progress["played"] / progress["total"])
                if words[:k]:
                    spoken.append(" ".join(words[:k]))
            said = " ".join(spoken).strip()
            if said:
                self._segment("agent", said, interrupted=m.interrupted)
                self.messages.append({"role": "assistant", "content": said})
            self._record_metrics(m)
            if not self.ended.is_set() and self.state != "listening":
                self._set_state("listening")
            self.silent_ms = 0
            await self._flush()

    # ------------------------------------------------------------------ escalation
    def _escalation_trigger(self, text: str) -> str | None:
        """A phrase the caller said, or "unclear" after too many turns with nothing understood."""
        esc = self.escalation
        if not esc.get("enabled"):
            return None
        if not text:
            self.unclear_turns += 1
            limit = int(esc.get("max_unclear_turns") or 0)
            return "unclear" if limit and self.unclear_turns >= limit else None
        self.unclear_turns = 0
        said = " ".join(text.lower().split())
        return next((p for p in esc.get("phrases", []) if p in said), None)

    def _escalate(self, trigger: str) -> None:
        """Hands the call over. On a phone call with transfer numbers, the caller is transferred (SIP REFER) to the
        first one; on a browser call the agent says the hand-over message and ends the call with a reason that says
        what was asked for."""
        action = self.escalation.get("action", "take_message")
        EVENTS.labels("escalation").inc()
        self._event("escalation.requested", {"trigger": trigger, "action": action, "turn": self.turn_no})
        message = self.escalation.get("message") or "Thank you for calling."
        if action == "transfer" and self.tel.get("can_transfer"):
            asyncio.get_running_loop().create_task(self._transfer(message))
            return
        reason = "transfer_requested" if action == "transfer" else "escalated"
        asyncio.get_running_loop().create_task(self._final_words(message, reason))

    async def _transfer(self, announce: str) -> None:
        if self.closing:
            return
        self.closing = True  # nothing else may speak or end the call while the hand-over runs
        if self.responding and self.respond_task is not asyncio.current_task():
            self.respond_task.cancel()  # type: ignore[union-attr]
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.respond_task  # type: ignore[misc]
        self.interruptible = False
        with contextlib.suppress(NoProviderError, CallEndedError, Exception):
            await self._respond(None, preset=announce, kind="system")
        try:
            r = await self.backend.transfer(0)
            ok = bool(r.get("ok"))
        except CallEndedError:
            ok = True  # the carrier already ended our leg: the caller is with the other number
        except Exception:  # noqa: BLE001 - the caller stays with the agent
            ok = False
        if ok:
            EVENTS.labels("transfer").inc()
            self.end("transferred")
            return
        self._event("escalation.requested", {"trigger": "transfer_failed", "action": "take_message"})
        self.closing = False
        self.interruptible = bool(self.cfg.get("interruptible", True))
        with contextlib.suppress(NoProviderError, CallEndedError, Exception):
            await self._respond(None, preset=self.msg["transfer_failed"], kind="system")

    # ------------------------------------------------------------------ opt-out and consent (phone calls)
    def _opted_out(self, text: str) -> bool:
        said = " ".join(text.lower().replace("’", "'").split())
        if not any(p in said for p in self.opt_out_phrases):
            return False
        EVENTS.labels("opt_out").inc()
        self._event("opt_out.requested", {"turn": self.turn_no})
        loop = asyncio.get_running_loop()

        async def go() -> None:
            with contextlib.suppress(Exception):
                await self.backend.opt_out(text[:200])
            await self._final_words(self.msg["opted_out"], "opted_out")

        loop.create_task(go())
        return True

    def _consent_answer(self, text: str) -> None:
        """The first thing the caller says after the recording notice: a refusal stops recording consent."""
        self.consent_pending = False
        words = set(" ".join(text.lower().replace("’", "'").split()).replace(",", " ").replace(".", " ").split())
        status = "declined" if words & DECLINE_WORDS else "granted"
        self._event("recording.consent", {"status": status})
        asyncio.get_running_loop().create_task(self._safe(self.backend.consent("recording", status, text[:200])))

    async def _uninterrupted(self, text: str) -> None:
        before, self.interruptible = self.interruptible, False
        try:
            await self._respond(None, preset=text, kind="greeting")
        finally:
            self.interruptible = before

    async def _safe(self, coro: Any) -> None:
        with contextlib.suppress(Exception):
            await coro

    # ------------------------------------------------------------------ keypad (DTMF)
    async def _keypad(self) -> None:
        """Keypad tones: 0 asks for a person; other keys are collected and sent as one typed reply after # or a
        short pause, so "press 1 for..." flows and account numbers both work."""
        q: asyncio.Queue[str] = self.channel.dtmf  # type: ignore[attr-defined]
        while not self.ended.is_set():
            try:
                digit = await asyncio.wait_for(q.get(), KEYPAD_PAUSE_S / self.speed if self.keys else None)
            except TimeoutError:
                digit = "#"
            self._event("dtmf", {"digit": digit})
            if digit == "0" and not self.keys and self.escalation.get("enabled"):
                self._escalate("keypad_0")
                continue
            if digit != "#":
                self.keys = (self.keys + digit)[-20:]
                continue
            keys, self.keys = self.keys, ""
            if keys and not self.closing:
                if self.responding:
                    await self._barge_in()
                self._start(self._respond(None, typed=" ".join(keys)))

    async def _transcribe(self, utt: Utterance, m: TurnMetrics) -> str:
        t = self.clock()
        r = await self.backend.stt(to_wav(utt.pcm), self.lang, self._req("stt"))
        m.stt_ms = self._wall_ms(t)
        m.providers["stt"] = f"{r.provider} / {r.model}"
        text = (r.text or "").strip()
        if text:
            self._segment("caller", text, start_ms=utt.start_ms, end_ms=utt.end_ms)
            self.messages.append({"role": "user", "content": text})
            await self.channel.send({"type": "transcript", "speaker": "caller", "text": text})
        return text

    async def _llm_clauses(self, m: TurnMetrics) -> AsyncIterator[str]:
        t = self.clock()
        loop = asyncio.get_running_loop()
        info: dict = {"on_tool": lambda tool: loop.create_task(self.channel.send({"type": "tool", **tool}))}
        splitter = ClauseSplitter()
        async for delta in self.backend.llm(list(self.messages), self.lang, self._req("llm"), info):
            if m.llm_first_token_ms is None:
                m.llm_first_token_ms = self._wall_ms(t)
            for c in splitter.feed(delta):
                yield c
        for c in splitter.flush():
            yield c
        m.llm_total_ms = self._wall_ms(t)
        if info.get("provider"):
            m.providers["llm"] = f"{info['provider']} / {info.get('model')}"
        if info.get("tools"):
            m.tools = [x["name"] for x in info["tools"] if x.get("status") != "running"]

    async def _preset_clauses(self, text: str) -> AsyncIterator[str]:
        splitter = ClauseSplitter()
        for c in splitter.feed(text) + splitter.flush():
            yield c

    async def _speak(
        self, clauses: AsyncIterator[str], m: TurnMetrics, t0: float, spoken: list[str], progress: dict
    ) -> None:
        """Synthesizes clause N+1 while clause N plays, so audio flows without gaps."""
        queue: asyncio.Queue[tuple[str, bytes] | None] = asyncio.Queue(maxsize=2)

        async def produce() -> None:
            try:
                async for clause in clauses:
                    t = self.clock()
                    r = await self.backend.tts(clause, self.lang, self.voice, self._req("tts"))
                    if m.tts_first_audio_ms is None:
                        m.tts_first_audio_ms = self._wall_ms(t)
                        m.providers["tts"] = f"{r.provider} / {r.model}"
                    await queue.put((clause, from_wav(r.audio or b"")))
            finally:
                await queue.put(None)

        producer = asyncio.create_task(produce())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                clause, pcm = item
                if self.state != "speaking":
                    self._set_state("speaking")
                await self.channel.send({"type": "transcript", "speaker": "agent", "text": clause, "partial": True})
                fr = split_frames(pcm)
                progress.update(clause=clause, played=0, total=len(fr))
                for f in fr:
                    await self.channel.write_frame(f)
                    if m.first_audible_ms is None:
                        m.first_audible_ms = self._wall_ms(t0)
                    progress["played"] += 1
                spoken.append(clause)
                progress.update(clause="", played=0, total=0)
            await producer  # surfaces provider errors
        finally:
            if not producer.done():
                producer.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await producer

    # ------------------------------------------------------------------ recording
    def _segment(self, speaker: str, text: str, **kw: Any) -> None:
        self.segments.append({"seq": self.seq, "speaker": speaker, "text": text, "language": self.lang, **kw})
        self.seq += 1

    def _event(self, type_: str, data: dict) -> None:
        self.event_no += 1
        self.events.append({"key": f"{self.rid}:{self.event_no}:{type_}", "type": type_, "data": data})

    def _record_metrics(self, m: TurnMetrics) -> None:
        self.metrics.append(m)
        self._event("turn.metrics", m.as_dict())
        for stage in ("stt_ms", "llm_first_token_ms", "tts_first_audio_ms", "first_audible_ms"):
            v = getattr(m, stage)
            if v is not None and not m.interrupted:
                STAGE.labels(stage.removesuffix("_ms")).observe(v / 1000)

    async def _flush(self, final: bool = False) -> None:
        if not self.events and not self.segments:
            return
        events, segments = self.events, self.segments
        self.events, self.segments = [], []
        try:
            await self.backend.record(events, segments)
        except Exception:  # keep them for the next flush; recording must never break the conversation
            log.warning("call %s: recording failed, will retry", self.boot.call_id)
            self.events, self.segments = events + self.events, segments + self.segments
            if final:
                raise
