# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""OpenAI-compatible API: OpenAI itself, and self-hosted servers that speak the same protocol (Ollama's /v1,
Faster-Whisper servers exposing /v1/audio/transcriptions). Chat uses streaming with include_usage so token counts
come from the provider, not estimates."""

import json
from collections.abc import AsyncIterator

import httpx

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
    http,
    raise_for,
    wav_seconds,
)


def _headers(ep: Endpoint) -> dict[str, str]:
    return {"Authorization": f"Bearer {ep.secret}"} if ep.secret else {}


class OpenAIChat(LLMAdapter):
    async def stream_chat(self, ep: Endpoint, req: LLMRequest) -> AsyncIterator[LLMEvent]:
        body = {
            "model": req.model,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        try:
            async with http().stream("POST", f"{ep.base_url}/chat/completions", json=body, headers=_headers(ep)) as r:
                if not r.is_success:
                    await r.aread()
                    raise_for(r, "openai")
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    for choice in chunk.get("choices") or []:
                        text = (choice.get("delta") or {}).get("content")
                        if text:
                            yield TextDelta(text)
                    usage = chunk.get("usage")
                    if usage:
                        yield LLMUsage(int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))
        except httpx.TransportError as e:
            raise ProviderError(f"openai: connection failed ({type(e).__name__})") from None

    async def verify(self, ep: Endpoint) -> bool | None:
        try:
            r = await http().get(f"{ep.base_url}/models", headers=_headers(ep))
        except httpx.TransportError:
            return False
        return r.is_success


class OpenAITranscribe(STTAdapter):
    async def transcribe(self, ep: Endpoint, *, model: str, audio: bytes, mime: str, language: str | None) -> STTResult:
        data = {"model": model, "response_format": "verbose_json"}
        if language:
            data["language"] = language.split("-")[0]  # ISO-639-1 code
        try:
            r = await http().post(
                f"{ep.base_url}/audio/transcriptions",
                headers=_headers(ep),
                data=data,
                files={"file": ("audio", audio, mime)},
            )
        except httpx.TransportError as e:
            raise ProviderError(f"openai-stt: connection failed ({type(e).__name__})") from None
        raise_for(r, "openai-stt")
        body = r.json()
        seconds = body.get("duration") or wav_seconds(audio) or 0.0
        return STTResult(text=body.get("text", ""), language=body.get("language"), audio_seconds=float(seconds))

    async def verify(self, ep: Endpoint) -> bool | None:
        return await OpenAIChat().verify(ep)


class OpenAISpeech(TTSAdapter):
    async def synthesize(
        self, ep: Endpoint, *, model: str, text: str, voice: str | None, language: str | None
    ) -> TTSResult:
        body = {"model": model, "input": text, "voice": voice or "alloy", "response_format": "mp3"}
        try:
            r = await http().post(f"{ep.base_url}/audio/speech", headers=_headers(ep), json=body)
        except httpx.TransportError as e:
            raise ProviderError(f"openai-tts: connection failed ({type(e).__name__})") from None
        raise_for(r, "openai-tts")
        return TTSResult(audio=r.content, mime="audio/mpeg", characters=len(text))

    async def verify(self, ep: Endpoint) -> bool | None:
        return await OpenAIChat().verify(ep)
