# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Calls (M08) and browser voice sessions (M10). A browser test call goes through exactly the engine, agent
version and metering that a phone call will use (MP section 6); only the way audio enters the room differs."""

import secrets
from uuid import UUID

import redis
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select, text

from ...core.config import get_settings
from ...core.context import Ctx, require
from ...core.db import set_context
from ...core.errors import ApiError, conflict, not_found
from ...core.permissions import Perm
from ..m05_agents.models import Agent, AgentVersion
from ..m05_agents.router import get_agent
from . import dispatch, lifecycle
from .livekit import room_token
from .models import Call, CallEvent, TranscriptSegment
from .schemas import CallDetailOut, CallOut, EventOut, SegmentOut, VoiceSessionIn, VoiceSessionOut

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
    )


@router.post("/v1/voice/sessions", response_model=VoiceSessionOut, status_code=status.HTTP_201_CREATED)
def start_browser_call(data: VoiceSessionIn, ctx: Ctx = Depends(require(Perm.CALLS_TEST))) -> VoiceSessionOut:
    s = get_settings()
    agent, version = get_agent(ctx, data.agent_id)
    if agent.status != "active":
        raise not_found()
    ctx.session.execute(STALE_SQL, {"t": ctx.tenant.id})
    live = ctx.session.scalar(
        select(func.count())
        .select_from(Call)
        .where(Call.tenant_id == ctx.tenant.id, Call.status.not_in(lifecycle.TERMINAL))
    )
    if (live or 0) >= s.max_concurrent_calls_per_tenant:
        raise ApiError(429, "too_many_calls", "Your organisation already has the maximum number of live calls")
    max_seconds = min(int(version.config.get("max_call_seconds", 300)), s.max_call_seconds)
    call = Call(
        tenant_id=ctx.tenant.id,
        agent_id=agent.id,
        agent_version_id=version.id,
        channel="browser",
        direction="test",
        status="created",
        room_name=f"call_{secrets.token_urlsafe(18)}",  # opaque: no tenant, agent or user in the name
        correlation_id=ctx.meta.correlation_id or secrets.token_hex(16),
        language=version.config.get("language"),
        created_by_membership_id=ctx.membership.id,
    )
    ctx.session.add(call)
    ctx.session.flush()
    ctx.audit("call.started", resource_type="call", resource_id=str(call.id), channel="browser", agent=str(agent.id))
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
    if c.status in ("created", "dispatching"):
        lifecycle.move(c, "abandoned", "user_ended")
    else:
        lifecycle.move(c, "ending")
    ctx.audit("call.end_requested", resource_type="call", resource_id=str(c.id))
    try:
        dispatch.control(c.id, "hangup")
    except redis.RedisError:
        pass  # the worker also ends the call when the caller leaves the room
