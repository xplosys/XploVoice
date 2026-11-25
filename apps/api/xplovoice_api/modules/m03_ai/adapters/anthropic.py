# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Anthropic Messages API with streaming. Input tokens arrive in message_start, output tokens in message_delta."""

import json
from collections.abc import AsyncIterator

import httpx

from .base import (
    ChatMessage,
    Endpoint,
    LLMAdapter,
    LLMEvent,
    LLMRequest,
    LLMUsage,
    ProviderError,
    TextDelta,
    ToolCall,
    http,
    parse_arguments,
    raise_for,
)

VERSION = "2023-06-01"


def _headers(ep: Endpoint) -> dict[str, str]:
    return {"x-api-key": ep.secret or "", "anthropic-version": VERSION}


def _messages(msgs: list[ChatMessage]) -> list[dict]:
    """Anthropic wants tool results as user content blocks, consecutive results in one message."""
    out: list[dict] = []
    for m in msgs:
        if m.role == "system":
            continue
        if m.role == "tool":
            block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue
        if m.tool_calls:
            blocks: list[dict] = [{"type": "text", "text": m.content}] if m.content else []
            blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in m.tool_calls]
            out.append({"role": "assistant", "content": blocks})
            continue
        out.append({"role": m.role, "content": m.content})
    return out


class AnthropicChat(LLMAdapter):
    async def stream_chat(self, ep: Endpoint, req: LLMRequest) -> AsyncIterator[LLMEvent]:
        system = "\n\n".join(m.content for m in req.messages if m.role == "system")
        body: dict = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "messages": _messages(req.messages),
            "stream": True,
        }
        if system:
            body["system"] = system
        if req.tools:
            body["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in req.tools
            ]
        blocks: dict[int, dict] = {}
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
                    elif t == "content_block_start" and ev.get("content_block", {}).get("type") == "tool_use":
                        cb = ev["content_block"]
                        blocks[int(ev.get("index", 0))] = {
                            "id": cb.get("id", ""),
                            "name": cb.get("name", ""),
                            "json": "",
                        }
                    elif t == "content_block_delta" and ev.get("delta", {}).get("type") == "input_json_delta":
                        b = blocks.get(int(ev.get("index", 0)))
                        if b is not None:
                            b["json"] += ev["delta"].get("partial_json", "")
                    elif t == "content_block_stop" and int(ev.get("index", -1)) in blocks:
                        b = blocks.pop(int(ev["index"]))
                        yield ToolCall(b["id"], b["name"], parse_arguments(b["json"]))
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
