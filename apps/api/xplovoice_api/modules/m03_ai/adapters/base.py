# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Provider adapter contract (M03). Every vendor is wrapped behind one of three interfaces so the gateway can
route, fail over and meter without knowing vendor details. Adapters never see tenant data beyond the request,
never log request content, and report usage in the provider's own units (MP section 22)."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

import httpx

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class LLMRequest:
    model: str
    messages: list[ChatMessage]
    max_tokens: int = 512
    temperature: float = 0.4


@dataclass
class TextDelta:
    text: str


@dataclass
class LLMUsage:
    input_tokens: int
    output_tokens: int


LLMEvent = TextDelta | LLMUsage


@dataclass
class STTResult:
    text: str
    language: str | None
    audio_seconds: float


@dataclass
class TTSResult:
    audio: bytes
    mime: str
    characters: int


@dataclass(frozen=True)
class Endpoint:
    """Where and how to call a provider. The secret is resolved by the gateway and never leaves the server."""

    base_url: str
    secret: str | None
    extra: dict[str, str] = field(default_factory=dict)


class ProviderError(Exception):
    """A provider call failed. availability=True means the provider (not the request) is the problem: it
    counts toward the circuit breaker and is worth retrying or failing over."""

    def __init__(
        self, message: str, *, status: int | None = None, availability: bool = True, retryable: bool = True
    ) -> None:
        super().__init__(message)
        self.status = status
        self.availability = availability
        self.retryable = retryable


def raise_for(resp: httpx.Response, provider: str) -> None:
    """Map an HTTP error to ProviderError without including response bodies (they can echo user content)."""
    if resp.is_success:
        return
    code = resp.status_code
    if code in (401, 403):
        raise ProviderError(
            f"{provider}: credentials rejected ({code})", status=code, availability=False, retryable=False
        )
    if code == 429:
        raise ProviderError(f"{provider}: rate limited", status=code, availability=False, retryable=True)
    if code >= 500:
        raise ProviderError(f"{provider}: server error ({code})", status=code)
    raise ProviderError(f"{provider}: request rejected ({code})", status=code, availability=False, retryable=False)


class LLMAdapter:
    async def stream_chat(self, ep: Endpoint, req: LLMRequest) -> AsyncIterator[LLMEvent]:
        raise NotImplementedError
        yield  # pragma: no cover

    async def verify(self, ep: Endpoint) -> bool | None:
        """Cheap credential check. None means the provider offers no safe way to check."""
        return None


class STTAdapter:
    async def transcribe(self, ep: Endpoint, *, model: str, audio: bytes, mime: str, language: str | None) -> STTResult:
        raise NotImplementedError

    async def verify(self, ep: Endpoint) -> bool | None:
        return None


class TTSAdapter:
    async def synthesize(
        self, ep: Endpoint, *, model: str, text: str, voice: str | None, language: str | None
    ) -> TTSResult:
        raise NotImplementedError

    async def verify(self, ep: Endpoint) -> bool | None:
        return None


_client: httpx.AsyncClient | None = None


def http() -> httpx.AsyncClient:
    """Shared client. Tests swap the transport with set_transport()."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0), follow_redirects=False)
    return _client


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    global _client
    _client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(30.0, connect=5.0)) if transport else None


def wav_seconds(audio: bytes) -> float | None:
    """Duration of a PCM WAV file from its header, used when a provider does not report duration."""
    import io
    import wave

    try:
        with wave.open(io.BytesIO(audio)) as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, EOFError):
        return None


def pcm16_to_wav(pcm: bytes, rate: int) -> bytes:
    """Wraps raw 16-bit mono PCM in a WAV header. Voice calls need uncompressed audio they can stream."""
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()
