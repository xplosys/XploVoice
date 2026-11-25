# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Anthropic Messages API with streaming. Input tokens arrive in message_start, output tokens in message_delta."""

import json
from collections.abc import AsyncIterator

import httpx

from .base import Endpoint, LLMAdapter, LLMEvent, LLMRequest, LLMUsage, ProviderError, TextDelta, http, raise_for

VERSION = "2023-06-01"


def _headers(ep: Endpoint) -> dict[str, str]:
    return {"x-api-key": ep.secret or "", "anthropic-version": VERSION}


class AnthropicChat(LLMAdapter):
    async def stream_chat(self, ep: Endpoint, req: LLMRequest) -> AsyncIterator[LLMEvent]:
        system = "\n\n".join(m.content for m in req.messages if m.role == "system")
        body: dict = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages if m.role != "system"],
            "stream": True,
        }
        if system:
            body["system"] = system
        input_tokens = 0
        try:
            async with http().stream("POST", f"{ep.base_url}/v1/messages", json=body, headers=_headers(ep)) as r:
                if not r.is_success:
                    await r.aread()
                    raise_for(r, "anthropic")
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    ev = json.loads(line[5:].strip())
                    t = ev.get("type")
                    if t == "message_start":
                        input_tokens = int(ev["message"].get("usage", {}).get("input_tokens", 0))
                    elif t == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                        yield TextDelta(ev["delta"]["text"])
                    elif t == "message_delta":
                        out = int(ev.get("usage", {}).get("output_tokens", 0))
                        yield LLMUsage(input_tokens, out)
                    elif t == "error":
                        raise ProviderError(f"anthropic: stream error ({ev.get('error', {}).get('type')})")
        except httpx.TransportError as e:
            raise ProviderError(f"anthropic: connection failed ({type(e).__name__})") from None

    async def verify(self, ep: Endpoint) -> bool | None:
        try:
            r = await http().get(f"{ep.base_url}/v1/models", headers=_headers(ep))
        except httpx.TransportError:
            return False
        return r.is_success
