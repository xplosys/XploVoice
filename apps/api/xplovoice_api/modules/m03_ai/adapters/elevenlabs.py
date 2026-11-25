# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""ElevenLabs text-to-speech. Billed in characters, which the adapter reports as len(text). Requests 16 kHz PCM,
returned as WAV, so voice calls can play it without decoding a compressed format."""

import httpx

from .base import Endpoint, ProviderError, TTSAdapter, TTSResult, http, pcm16_to_wav, raise_for


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
                params={"output_format": "pcm_16000"},
                headers={"xi-api-key": ep.secret or ""},
            )
        except httpx.TransportError as e:
            raise ProviderError(f"elevenlabs: connection failed ({type(e).__name__})") from None
        raise_for(r, "elevenlabs")
        return TTSResult(audio=pcm16_to_wav(r.content, 16000), mime="audio/wav", characters=len(text))

    async def verify(self, ep: Endpoint) -> bool | None:
        try:
            r = await http().get(f"{ep.base_url}/v1/user", headers={"xi-api-key": ep.secret or ""})
        except httpx.TransportError:
            return False
        return r.is_success
