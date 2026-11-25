# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""One agent reply, server side: retrieval, the actions already taken on the call, the model, and any tool calls
it makes, looped until the model answers in words (addendum B: "authorized tool execution, when needed").

Voice calls (through the worker's internal API) and text test chats use this same function, so what an agent
can read and do is decided in one place, on the server, never by a worker."""

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..m03_ai import gateway
from ..m03_ai.adapters.base import ChatMessage, LLMRequest, ToolCall
from ..m05_agents.schemas import AgentConfig
from ..m11_workflows.service import Actor
from ..m12_knowledge.service import reference_block, search
from . import gateway as tools

MAX_TOOL_ROUNDS = 3  # then the model must answer in words
TOOL_LABELS = {
    "check_availability": "Checking availability",
    "book_appointment": "Booking the appointment",
    "reschedule_appointment": "Rescheduling",
    "cancel_appointment": "Cancelling",
    "create_lead": "Saving your details",
    "create_ticket": "Creating a ticket",
    "lookup_order": "Looking up the order",
    "send_sms_confirmation": "Sending a confirmation",
}


@dataclass
class Turn:
    tenant_id: UUID
    country: str
    business_name: str
    call_id: UUID
    version_id: UUID
    cfg: AgentConfig
    source: str  # call | chat
    info: dict[str, Any] = field(default_factory=dict)  # filled in: retrieval, tools, provider


async def respond(
    turn: Turn,
    s: Session,
    messages: list[ChatMessage],
    *,
    language: str | None,
    request_id: str,
    meter: Callable[[int], gateway.Meter],
    outcome: gateway.Outcome,
    max_tokens: int = 300,
) -> AsyncIterator[dict[str, Any]]:
    """Yields {"t": text} and {"tool": {...}} events. Raises gateway.NoProviderAvailableError like chat_stream."""
    msgs = list(messages)
    user_text = next((m.content for m in reversed(msgs) if m.role == "user"), "")
    extra: list[ChatMessage] = []
    if turn.cfg.knowledge_base_ids and user_text:
        hits = await run_in_threadpool(search, s, list(turn.cfg.knowledge_base_ids), user_text, source=turn.source)
        turn.info["retrieval"] = [
            {
                "document_id": str(h.document_id),
                "chunk_id": h.chunk_id,
                "document": h.document,
                "score": round(h.score, 4),
            }
            for h in hits
        ]
        if hits:
            extra.append(ChatMessage("system", reference_block(hits)))
    note = await run_in_threadpool(tools.actions_note, s, turn.call_id)
    if note:
        extra.append(ChatMessage("system", note))
    head = 1 if msgs and msgs[0].role == "system" else 0
    msgs = msgs[:head] + extra + msgs[head:]
    offered = await run_in_threadpool(tools.specs, s, turn.cfg)
    actor = Actor(tenant_id=turn.tenant_id, country=turn.country, source=turn.source, call_id=turn.call_id)
    used: list[dict[str, Any]] = turn.info.setdefault("tools", [])

    for rnd in range(MAX_TOOL_ROUNDS + 1):
        specs = tuple(offered) if rnd < MAX_TOOL_ROUNDS else ()
        calls: list[ToolCall] = []
        said: list[str] = []
        req = LLMRequest(model="", messages=msgs, max_tokens=max_tokens, tools=specs)
        try:
            stream = gateway.chat_stream(
                meter(rnd), req, language=language, outcome=outcome, prefer=turn.cfg.ai.llm_model_id
            )
            async for ev in stream:
                if isinstance(ev, ToolCall):
                    calls.append(ev)
                else:
                    said.append(ev)
                    yield {"t": ev}
        except gateway.NoProviderAvailableError:
            if not specs or said or calls:
                raise
            offered = []  # no model that can use tools is reachable: answer without them rather than fail
            turn.info["tools_unavailable"] = True
            continue
        if not calls:
            return
        msgs.append(ChatMessage("assistant", "".join(said), tool_calls=tuple(calls)))
        for i, c in enumerate(calls[:4]):
            label = TOOL_LABELS.get(c.name, "Working on it")
            yield {"tool": {"name": c.name, "label": label, "status": "running"}}
            out = await tools.execute(
                actor=actor,
                cfg=turn.cfg,
                version_id=turn.version_id,
                key=c.name,
                args=c.arguments,
                idempotency_key=f"{turn.source}:{turn.call_id}:{request_id}:{rnd}:{i}",
                business_name=turn.business_name,
            )
            used.append({"name": c.name, "status": out.status, "execution_id": str(out.execution_id or "")})
            yield {"tool": {"name": c.name, "label": label, "status": out.status}}
            msgs.append(ChatMessage("tool", json.dumps(out.result, default=str)[:4000], tool_call_id=c.id))
        for c in calls[4:]:  # more than four in one go: refuse the rest so the model asks again
            msgs.append(ChatMessage("tool", json.dumps({"ok": False, "error": "too_many_tools"}), tool_call_id=c.id))
