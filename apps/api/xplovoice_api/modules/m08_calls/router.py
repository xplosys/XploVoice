# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Calls (M08) and browser voice sessions (M10). A browser test call goes through exactly the engine, agent
version and metering that a phone call will use (MP section 6); only the way audio enters the room differs."""

import secrets
from datetime import UTC, datetime
from uuid import UUID

import redis
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select, text
from starlette.concurrency import run_in_threadpool

from ...core.config import get_settings
from ...core.context import Ctx, require
from ...core.db import set_context
from ...core.errors import ApiError, conflict, not_found
from ...core.permissions import Perm
from ..m03_ai import gateway
from ..m03_ai.adapters.base import ChatMessage
from ..m05_agents.models import Agent, AgentVersion
from ..m05_agents.router import get_agent, get_version
from ..m05_agents.runtime import engine_config
from ..m05_agents.schemas import AgentConfig
from ..m09_tools import conversation
from . import dispatch, lifecycle
from .internal import escalate, record_turn
from .livekit import room_token
from .models import Call, CallEvent, TranscriptSegment
from .schemas import (
    CallDetailOut,
    CallOut,
    ChatIn,
    ChatReplyOut,
    ChatStartIn,
    ChatStartOut,
    EventOut,
    SegmentOut,
    VoiceSessionIn,
    VoiceSessionOut,
)

router = APIRouter(tags=["calls"])

# Calls that never got a worker (browser closed, no worker running) stop counting against the limit.
STALE_SQL = text(
    "update calls set status = 'abandoned', end_reason = 'not_joined', ended_at = now() "
    "where tenant_id = :t and status in ('created', 'dispatching', 'connecting') "
    "and created_at < now() - make_interval(secs => 120)"
)


def _call_out(c: Call, a: Agent, v: AgentVersion) -> dict:
    return dict(
        id=c.id,
        agent_id=a.id,
        agent_name=a.name,
        agent_version=v.version,
        channel=c.channel,
        direction=c.direction,
        status=c.status,
        end_reason=c.end_reason,
        language=c.language,
        created_at=c.created_at,
        connected_at=c.connected_at,
        ended_at=c.ended_at,
        duration_seconds=c.duration_seconds,
        recoveries=c.recoveries,
        agent_version_id=v.id,
        providers_used=c.providers_used or {},
    )


@router.post("/v1/voice/sessions", response_model=VoiceSessionOut, status_code=status.HTTP_201_CREATED)
def start_browser_call(data: VoiceSessionIn, ctx: Ctx = Depends(require(Perm.CALLS_TEST))) -> VoiceSessionOut:
    s = get_settings()
    agent, version = get_agent(ctx, data.agent_id)
    if agent.status == "archived":
        raise conflict("agent_archived", "This agent is archived. Restore it before testing it.")
    if data.version_id:
        version = get_version(ctx, agent, data.version_id)
    cfg = AgentConfig.model_validate(version.config)
    ctx.session.execute(STALE_SQL, {"t": ctx.tenant.id})
    live = ctx.session.scalar(
        select(func.count())
        .select_from(Call)
        .where(Call.tenant_id == ctx.tenant.id, Call.status.not_in(lifecycle.TERMINAL), Call.channel != "chat")
    )
    if (live or 0) >= s.max_concurrent_calls_per_tenant:
        raise ApiError(429, "too_many_calls", "Your organisation already has the maximum number of live calls")
    max_seconds = min(cfg.limits.max_call_seconds, s.max_call_seconds)
    call = Call(
        tenant_id=ctx.tenant.id,
        agent_id=agent.id,
        agent_version_id=version.id,
        channel="browser",
        direction="test",
        status="created",
        room_name=f"call_{secrets.token_urlsafe(18)}",  # opaque: no tenant, agent or user in the name
        correlation_id=ctx.meta.correlation_id or secrets.token_hex(16),
        language=cfg.language,
        created_by_membership_id=ctx.membership.id,
        options={"simulate_after_hours": True} if data.simulate_after_hours else {},
    )
    if agent.status == "draft":
        agent.status = "testing"  # MP section 9 lifecycle: the first test call moves a draft into testing
    ctx.session.add(call)
    ctx.session.flush()
    ctx.audit(
        "call.started",
        resource_type="call",
        resource_id=str(call.id),
        channel="browser",
        agent=str(agent.id),
        version=version.version,
    )
    ctx.session.commit()  # the worker must be able to read the call as soon as the job is visible
    set_context(ctx.session, tenant_id=ctx.tenant.id, user_id=ctx.user.id)  # RLS context is per transaction
    try:
        dispatch.enqueue(tenant_id=ctx.tenant.id, call_id=call.id, max_seconds=max_seconds)
    except redis.RedisError:
        lifecycle.move(call, "failed", "error")
        raise ApiError(503, "voice_unavailable", "Voice calls are unavailable right now. Try again shortly.") from None
    lifecycle.move(call, "dispatching")
    ttl = s.voice_token_minutes * 60
    token = room_token(f"caller-{call.id.hex[:12]}", call.room_name, ttl_seconds=ttl, name=ctx.user.display_name)
    return VoiceSessionOut(call_id=call.id, room=call.room_name, livekit_url=s.livekit_url, token=token, expires_in=ttl)


@router.get("/v1/calls", response_model=list[CallOut])
def list_calls(
    limit: int = Query(default=50, ge=1, le=200), ctx: Ctx = Depends(require(Perm.CALLS_READ))
) -> list[CallOut]:
    rows = ctx.session.execute(
        select(Call, Agent, AgentVersion)
        .join(Agent, Agent.id == Call.agent_id)
        .join(AgentVersion, AgentVersion.id == Call.agent_version_id)
        .where(Call.tenant_id == ctx.tenant.id)
        .order_by(Call.created_at.desc())
        .limit(limit)
    ).all()
    return [CallOut(**_call_out(c, a, v)) for c, a, v in rows]


def _get_call(ctx: Ctx, call_id: UUID) -> tuple[Call, Agent, AgentVersion]:
    row = ctx.session.execute(
        select(Call, Agent, AgentVersion)
        .join(Agent, Agent.id == Call.agent_id)
        .join(AgentVersion, AgentVersion.id == Call.agent_version_id)
        .where(Call.id == call_id, Call.tenant_id == ctx.tenant.id)
    ).first()
    if not row:
        raise not_found()
    return row[0], row[1], row[2]


@router.get("/v1/calls/{call_id}", response_model=CallDetailOut)
def read_call(call_id: UUID, ctx: Ctx = Depends(require(Perm.CALLS_READ))) -> CallDetailOut:
    c, a, v = _get_call(ctx, call_id)
    segs = ctx.session.scalars(
        select(TranscriptSegment).where(TranscriptSegment.call_id == c.id).order_by(TranscriptSegment.seq)
    )
    evs = ctx.session.scalars(select(CallEvent).where(CallEvent.call_id == c.id).order_by(CallEvent.id).limit(500))
    return CallDetailOut(
        **_call_out(c, a, v),
        transcript=[
            SegmentOut(
                seq=s.seq,
                speaker=s.speaker,
                text=s.text,
                language=s.language,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                interrupted=s.interrupted,
            )
            for s in segs
        ],
        events=[EventOut(type=e.type, data=e.data, occurred_at=e.occurred_at) for e in evs],
    )


@router.post("/v1/calls/{call_id}/end", status_code=status.HTTP_204_NO_CONTENT)
def end_call(call_id: UUID, ctx: Ctx = Depends(require(Perm.CALLS_TEST))) -> None:
    c, _, _ = _get_call(ctx, call_id)
    if c.status in lifecycle.TERMINAL:
        raise conflict("call_ended", "This call has already ended")
    if c.channel == "chat":
        lifecycle.move(c, "completed", "user_ended")  # no worker: a text chat ends at once
    elif c.status in ("created", "dispatching"):
        lifecycle.move(c, "abandoned", "user_ended")
    else:
        lifecycle.move(c, "ending")
    ctx.audit("call.end_requested", resource_type="call", resource_id=str(c.id))
    if c.channel == "chat":
        return
    try:
        dispatch.control(c.id, "hangup")
    except redis.RedisError:
        pass  # the worker also ends the call when the caller leaves the room


# ---------------------------------------------------------------------------------------------------- text chat
# A typed conversation with an agent: the same server-side reply pipeline as a voice call (retrieval, the tool
# gateway, metering), without speech. For testing knowledge and tools without a microphone or speech providers.
# It is recorded like a call (channel "chat"), but never counts as the voice test call that publishing needs.
STALE_CHATS = text(
    "update calls set status = 'completed', end_reason = 'silence_timeout', ended_at = now() "
    "where tenant_id = :t and channel = 'chat' and status = 'active' and created_at < now() - interval '2 hours'"
)


@router.post("/v1/agents/{agent_id}/chat", response_model=ChatStartOut, status_code=status.HTTP_201_CREATED)
def start_chat(agent_id: UUID, data: ChatStartIn, ctx: Ctx = Depends(require(Perm.CALLS_TEST))) -> ChatStartOut:
    agent, version = get_agent(ctx, agent_id)
    if agent.status == "archived":
        raise conflict("agent_archived", "This agent is archived. Restore it before testing it.")
    if data.version_id:
        version = get_version(ctx, agent, data.version_id)
    cfg = AgentConfig.model_validate(version.config)
    ctx.session.execute(STALE_CHATS, {"t": ctx.tenant.id})
    call = Call(
        tenant_id=ctx.tenant.id,
        agent_id=agent.id,
        agent_version_id=version.id,
        channel="chat",
        direction="test",
        status="active",
        room_name=f"chat_{secrets.token_urlsafe(18)}",
        correlation_id=ctx.meta.correlation_id or secrets.token_hex(16),
        language=cfg.language,
        created_by_membership_id=ctx.membership.id,
    )
    call.connected_at = datetime.now(UTC)
    ctx.session.add(call)
    ctx.session.flush()
    name = str(version.config.get("agent_name") or agent.name)
    greeting = cfg.greeting.strip()
    if greeting:
        ctx.session.add(
            TranscriptSegment(
                tenant_id=ctx.tenant.id, call_id=call.id, seq=0, speaker="agent", text=greeting, language=cfg.language
            )
        )
    ctx.audit(
        "call.started",
        resource_type="call",
        resource_id=str(call.id),
        channel="chat",
        agent=str(agent.id),
        version=version.version,
    )
    return ChatStartOut(call_id=call.id, agent_name=name, version=version.version, greeting=greeting or None)


@router.post("/v1/calls/{call_id}/chat", response_model=ChatReplyOut)
async def chat_message(call_id: UUID, data: ChatIn, ctx: Ctx = Depends(require(Perm.CALLS_TEST))) -> ChatReplyOut:
    def load() -> tuple[Call, conversation.Turn, list[ChatMessage], int, str | None]:
        c, a, v = _get_call(ctx, call_id)
        if c.channel != "chat":
            raise not_found()
        if c.status in lifecycle.TERMINAL:
            raise conflict("call_ended", "This chat has ended. Start a new one.")
        cfg = AgentConfig.model_validate(v.config)
        name = str(v.config.get("agent_name") or a.name)
        segs = ctx.session.scalars(
            select(TranscriptSegment).where(TranscriptSegment.call_id == c.id).order_by(TranscriptSegment.seq)
        ).all()
        if len(segs) >= 200:
            raise conflict("chat_too_long", "This chat is too long. Start a new one.")
        seq = (segs[-1].seq + 1) if segs else 0
        ctx.session.add(
            TranscriptSegment(
                tenant_id=ctx.tenant.id, call_id=c.id, seq=seq, speaker="caller", text=data.text, language=cfg.language
            )
        )
        ctx.session.flush()
        engine = engine_config(cfg, name, open_now=True, max_seconds_cap=get_settings().max_call_seconds)
        msgs = [ChatMessage("system", engine["instructions"] + "\n\nThis is a typed test chat.")]
        for g in segs:
            msgs.append(ChatMessage("user" if g.speaker == "caller" else "assistant", g.text))
        msgs.append(ChatMessage("user", data.text))
        trigger = _escalation(cfg, data.text)
        turn = conversation.Turn(
            tenant_id=ctx.tenant.id,
            country=ctx.tenant.country_code,
            business_name=ctx.tenant.name,
            call_id=c.id,
            version_id=v.id,
            cfg=cfg,
            source="chat",
        )
        return c, turn, msgs, seq + 1, (engine["escalation"]["message"] if trigger else None)

    c, turn, msgs, seq, escalation_message = await run_in_threadpool(load)
    request_id = f"chat-{secrets.token_hex(6)}"
    if escalation_message:

        def escalate_now() -> ChatReplyOut:
            set_context(ctx.session, tenant_id=ctx.tenant.id, user_id=ctx.user.id)
            ctx.session.add(
                TranscriptSegment(
                    tenant_id=ctx.tenant.id,
                    call_id=c.id,
                    seq=seq,
                    speaker="agent",
                    text=escalation_message,
                    language=c.language,
                )
            )
            ctx.session.add(
                CallEvent(
                    tenant_id=ctx.tenant.id,
                    call_id=c.id,
                    event_key=f"{request_id}:esc",
                    type="escalation.requested",
                    data={"trigger": "phrase", "action": "take_message"},
                )
            )
            ctx.session.flush()
            escalate(ctx.session, ctx.tenant.id, c.id, "phrase", "take_message")
            lifecycle.move(c, "completed", "escalated")
            return ChatReplyOut(reply=escalation_message, tools=[], retrieval=[], ended=True, end_reason="escalated")

        return await run_in_threadpool(escalate_now)
    outcome = gateway.Outcome("", "", "")
    parts: list[str] = []

    def meter(rnd: int) -> gateway.Meter:
        return gateway.Meter(
            session=ctx.session,
            tenant_id=ctx.tenant.id,
            idempotency_key=f"call:{c.id}:{request_id}:r{rnd}",
            source_type="call",
            source_id=str(c.id),
            correlation_id=c.correlation_id,
        )

    try:
        async for ev in conversation.respond(
            turn, ctx.session, msgs, language=c.language, request_id=request_id, meter=meter, outcome=outcome
        ):
            if "t" in ev:
                parts.append(ev["t"])
    except gateway.NoProviderAvailableError as e:
        raise ApiError(503, "no_provider_available", str(e)) from None
    reply = "".join(parts).strip() or "…"

    def save() -> ChatReplyOut:
        ctx.session.add(
            TranscriptSegment(
                tenant_id=ctx.tenant.id, call_id=c.id, seq=seq, speaker="agent", text=reply, language=c.language
            )
        )
        record_turn(ctx.session, ctx.tenant.id, c.id, request_id, turn.info)
        if outcome.provider:
            from .internal import _used

            _used(ctx.session, c, "llm", outcome)
        return ChatReplyOut(
            reply=reply,
            tools=turn.info.get("tools", []),
            retrieval=turn.info.get("retrieval", []),
            ended=False,
            end_reason=None,
        )

    return await run_in_threadpool(save)


def _escalation(cfg: AgentConfig, text_: str) -> bool:
    esc = cfg.escalation
    if not esc.enabled:
        return False
    said = " ".join(text_.lower().split())
    return any(p in said for p in esc.phrases)
