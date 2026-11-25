# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Deterministic mock provider for development and automated tests ONLY. The router refuses it in staging and
production. Failure can be injected through Endpoint.extra for failover tests."""

import io
import wave
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
    TTSAdapter,
    TTSResult,
    wav_seconds,
)

FAIL: set[str] = set()  # kinds that should fail, set by tests


def _fail(kind: str) -> None:
    if kind in FAIL:
        raise ProviderError(f"mock: injected {kind} failure", status=503)


class MockChat(LLMAdapter):
    async def stream_chat(self, ep: Endpoint, req: LLMRequest) -> AsyncIterator[LLMEvent]:
        _fail("llm")
        prompt = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
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
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:  # silent 16 kHz mono clip, 60 ms per word
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 960 * max(1, len(text.split())))
        return TTSResult(audio=buf.getvalue(), mime="audio/wav", characters=len(text))
