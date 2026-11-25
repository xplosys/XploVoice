# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""ElevenLabs text-to-speech. Billed in characters, which the adapter reports as len(text)."""

import httpx

from .base import Endpoint, ProviderError, TTSAdapter, TTSResult, http, raise_for


class ElevenLabsTTS(TTSAdapter):
    async def synthesize(
        self, ep: Endpoint, *, model: str, text: str, voice: str | None, language: str | None
    ) -> TTSResult:
        if not voice:
            raise ProviderError("elevenlabs: a voice id is required", availability=False, retryable=False)
        body: dict = {"text": text, "model_id": model}
        if language:
            body["language_code"] = language.split("-")[0]
        try:
            r = await http().post(
                f"{ep.base_url}/v1/text-to-speech/{voice}",
                json=body,
                params={"output_format": "mp3_44100_128"},
                headers={"xi-api-key": ep.secret or "", "Accept": "audio/mpeg"},
            )
        except httpx.TransportError as e:
            raise ProviderError(f"elevenlabs: connection failed ({type(e).__name__})") from None
        raise_for(r, "elevenlabs")
        return TTSResult(audio=r.content, mime="audio/mpeg", characters=len(text))

    async def verify(self, ep: Endpoint) -> bool | None:
        try:
            r = await http().get(f"{ep.base_url}/v1/user", headers={"xi-api-key": ep.secret or ""})
        except httpx.TransportError:
            return False
        return r.is_success
