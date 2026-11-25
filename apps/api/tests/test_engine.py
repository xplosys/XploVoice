# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Voice engine behaviour with synthetic audio and a fake platform backend (no LiveKit, no network).
Audio runs at 20x real time; turn-taking is measured in audio time, so results do not depend on speed."""

import asyncio

import pytest

from xplovoice_engine.audio import from_wav, silence, to_wav, tone
from xplovoice_engine.backend import AiResult, Bootstrap, NoProviderError
from xplovoice_engine.channel import ScriptedChannel
from xplovoice_engine.clauses import ClauseSplitter
from xplovoice_engine.session import MESSAGES, CallSession
from xplovoice_engine.turns import EnergyVad, TurnDetector

SPEED = 20.0
WORD_MS = 200


class FakeBackend:
    def __init__(self, reply: str = "Sure. Your appointment is moved to Friday at ten.", fail: set[str] | None = None):
        self.reply, self.fail = reply, fail or set()
        self.states: list[tuple[str, str | None]] = []
        self.events: list[dict] = []
        self.segments: list[dict] = []
        self.llm_messages: list[list[dict]] = []
        self.stt_calls = 0

    async def set_state(self, status, reason=None):
        self.states.append((status, reason))

    async def record(self, events=None, segments=None):
        self.events += events or []
        self.segments += segments or []

    async def stt(self, wav, language, request_id):
        if "stt" in self.fail:
            raise NoProviderError("stt")
        self.stt_calls += 1
        return AiResult("Mock", "mock-stt", text=f"caller turn {self.stt_calls}")

    async def llm(self, messages, language, request_id, info):
        if "llm" in self.fail:
            raise NoProviderError("llm")
        self.llm_messages.append(list(messages))
        for i, w in enumerate(self.reply.split(" ")):
            await asyncio.sleep(0.001)
            yield w if i == 0 else " " + w
        info.update(provider="Mock", model="mock-chat")

    async def tts(self, text, language, voice, request_id):
        if "tts" in self.fail:
            raise NoProviderError("tts")
        return AiResult(
            "Mock", "mock-tts", audio=to_wav(tone(WORD_MS * len(text.split()), 330, 1500)), mime="audio/wav"
        )


def boot(**cfg) -> Bootstrap:
    config = {
        "greeting": "Hello there.",
        "instructions": "Be brief.",
        "language": "en-IN",
        "max_call_seconds": 300,
        "silence_timeout_seconds": 15,
        "endpoint_silence_ms": 500,
        "barge_in_min_ms": 250,
        "interruptible": True,
    } | cfg
    return Bootstrap(
        "c1", "t1", "corr", "connecting", "Test agent", 1, config, "room", "ws://x", "tok", False, [], 0, 0.0
    )


def run(backend, script, b=None, tail_ms=1500):
    ch = ScriptedChannel(script, speed=SPEED, tail_ms=tail_ms)
    reason = asyncio.run(CallSession(backend, ch, b or boot(), worker_id="w-test").run())
    return reason, ch


def agent_lines(backend):
    return [s for s in backend.segments if s["speaker"] == "agent"]


def test_turn_detector_endpoints_after_silence_and_ignores_clicks():
    td = TurnDetector(EnergyVad(), endpoint_silence_ms=500)
    from xplovoice_engine.audio import frames

    out = [td.feed(f)[1] for f in frames(silence(300) + tone(60) + silence(700))]
    assert not any(out)  # 60 ms click is below the minimum speech length
    out = [td.feed(f)[1] for f in frames(tone(800) + silence(600))]
    utts = [u for u in out if u]
    assert len(utts) == 1 and 780 <= utts[0].end_ms - utts[0].start_ms <= 1020


def test_clause_splitter_starts_speech_on_first_clause():
    sp = ClauseSplitter()
    got = []
    for d in ["Sure", ".", " Your appointment", " is on Friday", ".", " Anything", " else?"]:
        got += sp.feed(d)
    assert got == ["Sure.", "Your appointment is on Friday."]
    assert sp.flush() == ["Anything else?"]


def test_full_conversation_turn():
    be = FakeBackend()
    reason, ch = run(be, [silence(2500), tone(900), silence(4000)])
    assert reason == "caller_hangup"
    assert be.states[0] == ("active", None) and be.states[-1] == ("completed", "caller_hangup")
    speakers = [(s["speaker"], s["text"]) for s in be.segments]
    assert speakers == [
        ("agent", "Hello there."),
        ("caller", "caller turn 1"),
        ("agent", "Sure. Your appointment is moved to Friday at ten."),
    ]
    assert [s["seq"] for s in be.segments] == [0, 1, 2]
    reply = [e["data"] for e in be.events if e["type"] == "turn.metrics" and e["data"]["kind"] == "reply"][0]
    for k in ("stt_ms", "llm_first_token_ms", "tts_first_audio_ms", "first_audible_ms", "endpoint_ms"):
        assert k in reply
    assert reply["providers"] == {"stt": "Mock / mock-stt", "llm": "Mock / mock-chat", "tts": "Mock / mock-tts"}
    # The model saw the caller's words after the greeting that was actually spoken.
    assert be.llm_messages[0][-2:] == [
        {"role": "assistant", "content": "Hello there."},
        {"role": "user", "content": "caller turn 1"},
    ]


def test_barge_in_cuts_reply_and_keeps_only_spoken_words():
    long_reply = " ".join(["word"] * 40) + "."  # one 8 second clause
    be = FakeBackend(reply=long_reply)
    # Caller asks, then interrupts about 2 s into the reply with 1 s of speech.
    reason, ch = run(be, [silence(1500), tone(800), silence(2500), tone(1000), silence(12000)])
    agent = agent_lines(be)
    interrupted = [a for a in agent if a["interrupted"]]
    assert len(interrupted) == 1
    n = len(interrupted[0]["text"].split())
    assert 3 <= n <= 15  # cut about 2 s in (10 words), not the full 40-word reply
    assert any(e["type"] == "barge_in" for e in be.events)
    # The second LLM call sees only what the caller heard of the interrupted reply.
    second = be.llm_messages[1]
    assert second[-2] == {"role": "assistant", "content": interrupted[0]["text"]}
    assert second[-1]["content"] == "caller turn 2"
    # The agent stopped talking soon after the caller started: well under the 8 s the reply would take.
    assert len(ch.heard) / 32000 < 30


def test_short_backchannel_does_not_interrupt():
    be = FakeBackend(reply=" ".join(["word"] * 20) + ".")
    run(be, [silence(1500), tone(800), silence(2000), tone(100), silence(6000)])
    assert not any(a["interrupted"] for a in agent_lines(be))
    assert not any(e["type"] == "barge_in" for e in be.events)


def test_not_interruptible_agent_finishes_its_reply():
    be = FakeBackend(reply=" ".join(["word"] * 20) + ".")
    run(be, [silence(1500), tone(800), silence(2000), tone(1000), silence(6000)], b=boot(interruptible=False))
    assert not any(a["interrupted"] for a in agent_lines(be))


@pytest.mark.parametrize("stage", ["stt", "llm"])
def test_no_provider_plays_fixed_message_and_ends(stage):
    be = FakeBackend(fail={stage})
    reason, _ = run(be, [silence(1500), tone(800), silence(5000)])
    assert reason == "no_provider" and be.states[-1] == ("failed", "no_provider")
    assert agent_lines(be)[-1]["text"] == MESSAGES["unavailable"]


def test_no_tts_ends_cleanly_without_audio():
    be = FakeBackend(fail={"tts"})
    reason, ch = run(be, [silence(3000)])
    assert reason == "no_provider" and len(ch.heard) == 0


def test_silence_prompts_then_ends():
    be = FakeBackend()
    reason, _ = run(be, [silence(1000)], b=boot(silence_timeout_seconds=5), tail_ms=20000)
    assert reason == "silence_timeout"
    texts = [a["text"] for a in agent_lines(be)]
    assert texts == ["Hello there.", MESSAGES["still_there"], MESSAGES["silence_bye"]]


def test_max_duration_guard():
    be = FakeBackend()
    reason, _ = run(be, [silence(1000)], b=boot(max_call_seconds=30, silence_timeout_seconds=60), tail_ms=60000)
    assert reason == "max_duration"
    assert agent_lines(be)[-1]["text"] == MESSAGES["time_limit"]


def test_resumed_call_keeps_history_and_apologises():
    be = FakeBackend()
    b = boot()
    b.resumed, b.next_seq = True, 5
    b.history = [{"speaker": "agent", "text": "Hello there."}, {"speaker": "caller", "text": "I need a cleaning."}]
    run(be, [silence(1500), tone(800), silence(4000)], b=b)
    assert be.segments[0] == {**be.segments[0], "speaker": "agent", "text": MESSAGES["resumed"], "seq": 5}
    assert {"role": "user", "content": "I need a cleaning."} in be.llm_messages[0]


def test_audio_roundtrip_resamples_to_16k():
    pcm24 = tone(500)  # pretend it is 24 kHz
    wav = to_wav(pcm24, 24000)
    assert abs(len(from_wav(wav)) - len(pcm24) * 16000 / 24000) <= 2
