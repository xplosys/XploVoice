# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Piper (self-hosted TTS) behind a small HTTP server: POST {base_url}?voice=... with the text as the body,
returning WAV. The URL comes only from platform configuration."""

import httpx

from .base import Endpoint, ProviderError, TTSAdapter, TTSResult, http, raise_for


class PiperTTS(TTSAdapter):
    async def synthesize(
        self, ep: Endpoint, *, model: str, text: str, voice: str | None, language: str | None
    ) -> TTSResult:
        try:
            r = await http().post(
                ep.base_url,
                params={"voice": voice or model},
                content=text.encode(),
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )
        except httpx.TransportError as e:
            raise ProviderError(f"piper: connection failed ({type(e).__name__})") from None
        raise_for(r, "piper")
        return TTSResult(audio=r.content, mime="audio/wav", characters=len(text))
