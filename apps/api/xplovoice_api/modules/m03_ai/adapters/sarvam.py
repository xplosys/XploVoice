# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Sarvam AI: speech-to-text and text-to-speech for Indian languages (Hindi, Indian English, and others)."""

import base64

import httpx

from .base import Endpoint, ProviderError, STTAdapter, STTResult, TTSAdapter, TTSResult, http, raise_for, wav_seconds


def _headers(ep: Endpoint) -> dict[str, str]:
    return {"api-subscription-key": ep.secret or ""}


class SarvamSTT(STTAdapter):
    async def transcribe(self, ep: Endpoint, *, model: str, audio: bytes, mime: str, language: str | None) -> STTResult:
        data = {"model": model, "language_code": language or "unknown"}
        try:
            r = await http().post(
                f"{ep.base_url}/speech-to-text",
                headers=_headers(ep),
                data=data,
                files={"file": ("audio.wav", audio, mime)},
            )
        except httpx.TransportError as e:
            raise ProviderError(f"sarvam-stt: connection failed ({type(e).__name__})") from None
        raise_for(r, "sarvam-stt")
        body = r.json()
        seconds = wav_seconds(audio)
        if seconds is None:
            raise ProviderError(
                "sarvam-stt: send WAV audio so duration can be metered", availability=False, retryable=False
            )
        return STTResult(text=body.get("transcript", ""), language=body.get("language_code"), audio_seconds=seconds)


class SarvamTTS(TTSAdapter):
    async def synthesize(
        self, ep: Endpoint, *, model: str, text: str, voice: str | None, language: str | None
    ) -> TTSResult:
        body: dict = {"text": text, "target_language_code": language or "hi-IN", "model": model}
        if voice:
            body["speaker"] = voice
        try:
            r = await http().post(f"{ep.base_url}/text-to-speech", headers=_headers(ep), json=body)
        except httpx.TransportError as e:
            raise ProviderError(f"sarvam-tts: connection failed ({type(e).__name__})") from None
        raise_for(r, "sarvam-tts")
        audios = r.json().get("audios") or []
        if not audios:
            raise ProviderError("sarvam-tts: empty response")
        return TTSResult(audio=base64.b64decode(audios[0]), mime="audio/wav", characters=len(text))
