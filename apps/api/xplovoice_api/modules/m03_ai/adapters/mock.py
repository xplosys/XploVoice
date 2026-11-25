# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Deterministic mock provider for development and automated tests ONLY. The router refuses it in staging and
production. Failure can be injected through Endpoint.extra for failover tests."""

import json
import math
import re
from collections.abc import AsyncIterator

from .base import (
    Endpoint,
    LLMAdapter,
    LLMEvent,
    LLMRequest,
    LLMUsage,
    ProviderError,
    STTAdapter,
    STTResult,
    TextDelta,
    ToolCall,
    TTSAdapter,
    TTSResult,
    pcm16_to_wav,
    wav_seconds,
)

FAIL: set[str] = set()  # kinds that should fail, set by tests


def _fail(kind: str) -> None:
    if kind in FAIL:
        raise ProviderError(f"mock: injected {kind} failure", status=503)


def _mock_tool(req: LLMRequest) -> ToolCall | None:
    """Deterministic stand-in for a model choosing tools, so tool flows can be tested and demonstrated without a
    vendor account. Keyword rules on the caller's last message; chains check_availability -> book_appointment."""
    names = {t.name for t in req.tools}
    if not names:
        return None
    last_user = max((i for i, m in enumerate(req.messages) if m.role == "user"), default=-1)
    if last_user < 0:
        return None
    said = req.messages[last_user].content
    low = said.lower()
    after = req.messages[last_user + 1 :]
    done = {c.name for m in after for c in m.tool_calls}
    results = {m.tool_call_id: m.content for m in after if m.role == "tool"}
    n = len(done)

    def call(name: str, args: dict) -> ToolCall | None:
        return ToolCall(f"mock_{n}_{name}", name, args) if name in names and name not in done else None

    name_m = re.search(r"my name is ([A-Za-z][A-Za-z .'-]{0,40}?)(?:[,.!?]|$| and )", said, re.I)
    phone_m = re.search(r"(\+?\d[\d -]{8,}\d)", said)
    name = name_m.group(1).strip() if name_m else "Test Caller"
    ref = re.search(r"\b([AT]-[A-Z0-9]{6})\b", said.upper())
    if "cancel" in low and ref:
        return call(
            "cancel_appointment", {"reference": ref.group(1)} | ({"phone": phone_m.group(1)} if phone_m else {})
        )
    if "book" in low or "appointment" in low or "available" in low:
        if "check_availability" not in done:
            return call("check_availability", {})
        if "book" in low and "book_appointment" not in done:
            avail = next((v for k, v in results.items() if k and "check_availability" in k), "{}")
            try:
                first = json.loads(avail).get("slots", [{}])[0].get("start")
            except (ValueError, IndexError, AttributeError):
                first = None
            if first:
                args = {"start": first, "name": name} | ({"phone": phone_m.group(1)} if phone_m else {})
                return call("book_appointment", args)
        return None
    if any(w in low for w in ("problem", "complaint", "broken", "not working", "issue")):
        return call("create_ticket", {"subject": said[:120], "description": said[:1000]})
    if any(w in low for w in ("call me back", "interested", "quote", "pricing")):
        args = {"name": name, "interest": said[:500], "wants_callback": "call me back" in low}
        return call("create_lead", args | ({"phone": phone_m.group(1)} if phone_m else {}))
    return None


class MockChat(LLMAdapter):
    async def stream_chat(self, ep: Endpoint, req: LLMRequest) -> AsyncIterator[LLMEvent]:
        _fail("llm")
        tool = _mock_tool(req)
        if tool:
            yield tool
            yield LLMUsage(sum(len(m.content.split()) for m in req.messages), 12)
            return
        prompt = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
        last = req.messages[-1] if req.messages else None
        ref = next((m.content for m in req.messages if m.role == "system" and m.content.startswith("Reference")), "")
        if last is not None and last.role == "tool":
            reply = f"[mock reply, development only] Tool result: {last.content[:300]}"
        elif ref:
            passage = ref.split(":\n", 1)[-1].split("\n\n")[0]
            reply = f"[mock reply, development only] From the knowledge base: {passage[:300]}"
        else:
            reply = f"[mock reply, development only] You said: {prompt[:200]}"
        words = reply.split(" ")
        for i, w in enumerate(words):
            yield TextDelta(w if i == 0 else " " + w)
        yield LLMUsage(sum(len(m.content.split()) for m in req.messages), len(words))

    async def verify(self, ep: Endpoint) -> bool | None:
        return True


class MockSTT(STTAdapter):
    async def transcribe(self, ep: Endpoint, *, model: str, audio: bytes, mime: str, language: str | None) -> STTResult:
        _fail("stt")
        seconds = wav_seconds(audio) or 0.0
        return STTResult(
            text=f"[mock transcript, development only] {seconds:.1f} seconds of audio",
            language=language,
            audio_seconds=seconds,
        )


class MockTTS(TTSAdapter):
    async def synthesize(
        self, ep: Endpoint, *, model: str, text: str, voice: str | None, language: str | None
    ) -> TTSResult:
        _fail("tts")
        # 16 kHz mono: a soft 180 ms tone and 60 ms gap per word, so a browser test call is audible.
        tone = b"".join(
            int(1500 * math.sin(2 * math.pi * 330 * i / 16000)).to_bytes(2, "little", signed=True) for i in range(2880)
        )
        word = tone + b"\x00\x00" * 960
        return TTSResult(
            audio=pcm16_to_wav(word * max(1, len(text.split())), 16000), mime="audio/wav", characters=len(text)
        )
