# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Deepgram pre-recorded transcription. Streaming (WebSocket) transcription arrives with the voice engine in
Phase 3; the adapter contract is the same."""

import httpx

from .base import Endpoint, ProviderError, STTAdapter, STTResult, http, raise_for, wav_seconds


class DeepgramSTT(STTAdapter):
    async def transcribe(self, ep: Endpoint, *, model: str, audio: bytes, mime: str, language: str | None) -> STTResult:
        params = {"model": model, "smart_format": "true"}
        if language:
            params["language"] = language
        try:
            r = await http().post(
                f"{ep.base_url}/v1/listen",
                params=params,
                content=audio,
                headers={"Authorization": f"Token {ep.secret}", "Content-Type": mime},
            )
        except httpx.TransportError as e:
            raise ProviderError(f"deepgram: connection failed ({type(e).__name__})") from None
        raise_for(r, "deepgram")
        body = r.json()
        alt = body["results"]["channels"][0]["alternatives"][0]
        seconds = body.get("metadata", {}).get("duration") or wav_seconds(audio) or 0.0
        detected = body["results"]["channels"][0].get("detected_language") or language
        return STTResult(text=alt.get("transcript", ""), language=detected, audio_seconds=float(seconds))

    async def verify(self, ep: Endpoint) -> bool | None:
        try:
            r = await http().get(f"{ep.base_url}/v1/projects", headers={"Authorization": f"Token {ep.secret}"})
        except httpx.TransportError:
            return False
        return r.is_success
