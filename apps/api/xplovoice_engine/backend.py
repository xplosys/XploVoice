# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""The engine's only route to the platform: the worker-scoped internal API (/internal/v1). Speech, model calls
and metering all go through the AI gateway there, so provider routing, failover, circuit breakers and usage are
identical for calls and for the playground."""

import base64
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx


class NoProviderError(Exception):
    """Every eligible provider failed or none is configured."""


class BackendError(Exception):
    pass


class CallEndedError(Exception):
    pass


@dataclass
class Bootstrap:
    call_id: str
    tenant_id: str
    correlation_id: str
    status: str
    agent_name: str
    agent_version: int
    config: dict[str, Any]
    room: str
    livekit_url: str
    livekit_token: str
    resumed: bool
    history: list[dict[str, str]]
    next_seq: int
    elapsed_seconds: float


@dataclass
class AiResult:
    provider: str
    model: str
    text: str | None = None
    audio: bytes | None = None
    mime: str | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)


class HttpBackend:
    def __init__(
        self,
        base_url: str,
        worker_key: str,
        call_id: str,
        call_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.call_id = call_id
        self.http = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/internal/v1/calls/{call_id}",
            headers={"X-Worker-Key": worker_key, "Authorization": f"Bearer {call_token}"},
            timeout=httpx.Timeout(timeout, connect=5.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    async def _post(self, path: str, body: dict) -> dict:
        r = await self.http.post(path, json=body)
        if r.status_code == 409:
            raise CallEndedError(path)
        if r.status_code == 503:
            raise NoProviderError(r.json().get("detail", {}).get("message", "no provider available"))
        if r.is_error:
            raise BackendError(f"{path}: HTTP {r.status_code}")
        return r.json()

    async def bootstrap(self, worker_id: str) -> Bootstrap:
        return Bootstrap(**(await self._post("/bootstrap", {"worker_id": worker_id})))

    async def set_state(self, status: str, reason: str | None = None) -> None:
        await self._post("/state", {"status": status, "reason": reason})

    async def record(self, events: list[dict] | None = None, segments: list[dict] | None = None) -> None:
        await self._post("/record", {"events": events or [], "segments": segments or []})

    async def stt(self, wav: bytes, language: str | None, request_id: str) -> AiResult:
        b = await self._post(
            "/stt",
            {
                "request_id": request_id,
                "audio_base64": base64.b64encode(wav).decode(),
                "mime": "audio/wav",
                "language": language,
            },
        )
        return AiResult(b["provider"], b["model"], text=b.get("text") or "", attempts=b["attempts"])

    async def tts(self, text: str, language: str | None, voice: str | None, request_id: str) -> AiResult:
        b = await self._post("/tts", {"request_id": request_id, "text": text, "language": language, "voice": voice})
        return AiResult(
            b["provider"], b["model"], audio=base64.b64decode(b["audio_base64"]), mime=b["mime"], attempts=b["attempts"]
        )

    async def llm(
        self, messages: list[dict[str, str]], language: str | None, request_id: str, info: dict
    ) -> AsyncIterator[str]:
        body = {"request_id": request_id, "messages": messages, "language": language}
        async with self.http.stream("POST", "/llm", json=body) as r:
            if r.status_code == 409:
                raise CallEndedError("llm")
            if r.is_error:
                raise BackendError(f"llm: HTTP {r.status_code}")
            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                ev = json.loads(line[6:])
                if "t" in ev:
                    yield ev["t"]
                elif "error" in ev:
                    raise NoProviderError(ev["error"])
                elif ev.get("done"):
                    info.update(provider=ev.get("provider"), model=ev.get("model"), units=ev.get("units"))
