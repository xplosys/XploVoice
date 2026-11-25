# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Internal API for voice workers (/internal/v1). Never exposed publicly: the reverse proxy routes it only on the
internal network. A worker presents the shared worker key AND a per-call token minted when the call was
dispatched; the token names one tenant and one call, and everything here runs under that tenant's RLS context.
Workers never hold tenant user tokens and never reach the database directly (LLD v1.3 section 5)."""

import asyncio
import base64
import binascii
import hmac
import json
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from ...core.config import get_settings
from ...core.db import session_scope
from ...core.errors import ApiError, bad_request, conflict, not_found, unauthorized
from ..m03_ai import gateway
from ..m03_ai.adapters.base import ChatMessage, LLMRequest
from ..m05_agents.models import Agent, AgentVersion
from ..m05_agents.runtime import engine_config, is_open
from ..m05_agents.schemas import AgentConfig
from . import lifecycle
from .dispatch import decode_worker_token
from .livekit import room_token
from .models import Call, CallEvent, TranscriptSegment
from .schemas import (
    BootstrapIn,
    BootstrapOut,
    HistoryItem,
    RecordIn,
    StateIn,
    WorkerAiOut,
    WorkerLlmIn,
    WorkerSttIn,
    WorkerTtsIn,
)

router = APIRouter(prefix="/internal/v1", tags=["internal"], include_in_schema=False)
bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Worker:
    tenant_id: UUID
    call_id: UUID


def worker_auth(
    call_id: UUID,
    x_worker_key: str | None = Header(default=None),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Worker:
    if not x_worker_key or not hmac.compare_digest(x_worker_key, get_settings().worker_key):
        raise unauthorized("worker_unauthorized", "Worker authentication required")
    if creds is None:
        raise unauthorized("worker_unauthorized", "Worker authentication required")
    try:
        claims = decode_worker_token(creds.credentials)
        tenant_id, token_call = UUID(claims["tid"]), UUID(claims["cid"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise unauthorized("worker_unauthorized", "Invalid worker token") from None
    if token_call != call_id:  # a token for one call can never act on another
        raise not_found()
    return Worker(tenant_id, call_id)


def _load(s, w: Worker) -> Call:  # type: ignore[no-untyped-def]
    call = s.scalar(select(Call).where(Call.id == w.call_id, Call.tenant_id == w.tenant_id))
    if not call:
        raise not_found()
    return call


def _agent_cfg(s, call: Call) -> AgentConfig:  # type: ignore[no-untyped-def]
    """The pinned version's configuration. Model preferences are read here, never taken from the worker."""
    v = s.get(AgentVersion, call.agent_version_id)
    assert v is not None
    return AgentConfig.model_validate(v.config)


def _used(s, call: Call, kind: str, o: gateway.Outcome) -> None:  # type: ignore[no-untyped-def]
    """Records the exact provider and model version that served this call (ADD-F-07). The last one wins if a
    failover changed it mid-call; every turn's providers are also in the turn.metrics events."""
    entry = {"provider": o.provider, "model": o.model, "model_version": o.model_key, "account": o.account}
    if (call.providers_used or {}).get(kind) != entry:  # atomic merge: STT, LLM and TTS requests overlap
        s.execute(
            text(
                "update calls set providers_used = providers_used "
                "|| jsonb_build_object(cast(:k as text), cast(:v as jsonb)) where id = :id"
            ),
            {"k": kind, "v": json.dumps(entry), "id": call.id},
        )


@router.post("/calls/{call_id}/bootstrap", response_model=BootstrapOut)
def bootstrap(call_id: UUID, data: BootstrapIn, w: Worker = Depends(worker_auth)) -> BootstrapOut:
    settings = get_settings()
    with session_scope(tenant_id=w.tenant_id) as s:
        call = _load(s, w)
        if call.status in lifecycle.TERMINAL:
            raise conflict("call_ended", "This call has already ended")
        agent = s.get(Agent, call.agent_id)
        version = s.get(AgentVersion, call.agent_version_id)
        assert agent and version
        resumed = call.connected_at is not None
        if resumed:
            call.recoveries += 1
        else:
            lifecycle.move(call, "connecting")
        s.execute(
            insert(CallEvent)
            .values(
                tenant_id=w.tenant_id,
                call_id=call.id,
                event_key=f"worker:{data.worker_id}:{call.recoveries}",
                type="worker.recovered" if resumed else "worker.joined",
                data={"worker": data.worker_id, "recoveries": call.recoveries},
            )
            .on_conflict_do_nothing()
        )
        segs = s.scalars(
            select(TranscriptSegment).where(TranscriptSegment.call_id == call.id).order_by(TranscriptSegment.seq)
        ).all()
        next_seq = (
            s.scalar(select(func.max(TranscriptSegment.seq)).where(TranscriptSegment.call_id == call.id)) or -1
        ) + 1
        cfg = AgentConfig.model_validate(version.config)
        name = str(version.config.get("agent_name") or agent.name)
        open_now = not (call.options or {}).get("simulate_after_hours") and is_open(
            cfg.business_hours, datetime.now(UTC)
        )
        if (call.options or {}).get("simulate_after_hours") and not cfg.business_hours.enabled:
            open_now = True  # nothing to simulate: the agent has no business hours
        config = engine_config(cfg, name, open_now=open_now, max_seconds_cap=settings.max_call_seconds)
        elapsed = (datetime.now(UTC) - call.connected_at).total_seconds() if call.connected_at else 0.0
        return BootstrapOut(
            call_id=call.id,
            tenant_id=w.tenant_id,
            correlation_id=call.correlation_id,
            status=call.status,
            agent_name=name,
            agent_version=version.version,
            config=config,
            room=call.room_name,
            livekit_url=settings.livekit_internal_url,
            livekit_token=room_token(
                "agent", call.room_name, ttl_seconds=config["max_call_seconds"] + 120, name=agent.name, agent=True
            ),
            resumed=resumed,
            history=[HistoryItem(speaker=x.speaker, text=x.text) for x in segs],
            next_seq=next_seq,
            elapsed_seconds=elapsed,
        )


@router.post("/calls/{call_id}/state")
def set_state(call_id: UUID, data: StateIn, w: Worker = Depends(worker_auth)) -> dict:
    with session_scope(tenant_id=w.tenant_id) as s:
        call = _load(s, w)
        before = call.status
        moved = lifecycle.move(call, data.status, data.reason)
        s.execute(
            insert(CallEvent)
            .values(
                tenant_id=w.tenant_id,
                call_id=call.id,
                event_key=f"state:{data.status}:{before}",
                type="state.changed" if moved else "state.ignored",
                data={"from": before, "to": data.status, "reason": data.reason},
            )
            .on_conflict_do_nothing()
        )
        return {"status": call.status, "moved": moved}


@router.post("/calls/{call_id}/record")
def record(call_id: UUID, data: RecordIn, w: Worker = Depends(worker_auth)) -> dict:
    """Idempotent: events are unique per key and segments per sequence number, so a retried or recovered
    worker can resend everything safely."""
    with session_scope(tenant_id=w.tenant_id) as s:
        _load(s, w)
        for e in data.events:
            s.execute(
                insert(CallEvent)
                .values(tenant_id=w.tenant_id, call_id=w.call_id, event_key=e.key, type=e.type, data=e.data)
                .on_conflict_do_nothing()
            )
        for g in data.segments:
            s.execute(
                insert(TranscriptSegment)
                .values(tenant_id=w.tenant_id, call_id=w.call_id, **g.model_dump())
                .on_conflict_do_nothing()
            )
    return {"ok": True}


def _meter(s, w: Worker, call: Call, request_id: str) -> gateway.Meter:  # type: ignore[no-untyped-def]
    return gateway.Meter(
        session=s,
        tenant_id=w.tenant_id,
        idempotency_key=f"call:{w.call_id}:{request_id}",
        source_type="call",
        source_id=str(w.call_id),
        correlation_id=call.correlation_id,
    )


def _no_provider(e: gateway.NoProviderAvailableError) -> ApiError:
    err = ApiError(503, "no_provider_available", str(e))
    err.detail["attempts"] = [asdict(a) for a in e.attempts]
    return err


@router.post("/calls/{call_id}/stt", response_model=WorkerAiOut)
async def stt(call_id: UUID, data: WorkerSttIn, w: Worker = Depends(worker_auth)) -> WorkerAiOut:
    try:
        audio = base64.b64decode(data.audio_base64, validate=True)
    except (binascii.Error, ValueError):
        raise bad_request("invalid_audio", "Audio must be base64 encoded") from None
    with session_scope(tenant_id=w.tenant_id) as s:
        call = _load(s, w)
        try:
            r, o = await gateway.transcribe(
                _meter(s, w, call, data.request_id),
                audio=audio,
                mime=data.mime,
                language=data.language,
                prefer=_agent_cfg(s, call).ai.stt_model_id,
            )
        except gateway.NoProviderAvailableError as e:
            raise _no_provider(e) from None
        _used(s, call, "stt", o)
    return WorkerAiOut(
        provider=o.provider,
        model=o.model,
        account=o.account,
        attempts=[asdict(a) for a in o.attempts],
        text=r.text,
        language=r.language,
    )


@router.post("/calls/{call_id}/tts", response_model=WorkerAiOut)
async def tts(call_id: UUID, data: WorkerTtsIn, w: Worker = Depends(worker_auth)) -> WorkerAiOut:
    with session_scope(tenant_id=w.tenant_id) as s:
        call = _load(s, w)
        try:
            r, o = await gateway.synthesize(
                _meter(s, w, call, data.request_id),
                text=data.text,
                language=data.language,
                voice=data.voice,
                prefer=_agent_cfg(s, call).ai.tts_model_id,
            )
        except gateway.NoProviderAvailableError as e:
            raise _no_provider(e) from None
        _used(s, call, "tts", o)
    return WorkerAiOut(
        provider=o.provider,
        model=o.model,
        account=o.account,
        attempts=[asdict(a) for a in o.attempts],
        audio_base64=base64.b64encode(r.audio).decode(),
        mime=r.mime,
    )


def _sse(obj: dict) -> bytes:
    return f"data: {json.dumps(obj, separators=(',', ':'))}\n\n".encode()


@router.post("/calls/{call_id}/llm")
async def llm(call_id: UUID, data: WorkerLlmIn, w: Worker = Depends(worker_auth)) -> StreamingResponse:
    """Streams the reply as server-sent events. When the worker disconnects (barge-in), the provider stream is
    closed and the tokens consumed so far are metered."""
    with session_scope(tenant_id=w.tenant_id) as s:
        _load(s, w)

    async def events() -> AsyncIterator[bytes]:
        with session_scope(tenant_id=w.tenant_id) as s:
            call = _load(s, w)
            outcome = gateway.Outcome("", "", "")
            req = LLMRequest(
                model="", messages=[ChatMessage(m.role, m.content) for m in data.messages], max_tokens=data.max_tokens
            )
            stream = gateway.chat_stream(
                _meter(s, w, call, data.request_id),
                req,
                language=data.language,
                outcome=outcome,
                prefer=_agent_cfg(s, call).ai.llm_model_id,
            )
            try:
                async for t in stream:
                    yield _sse({"t": t})
            except gateway.NoProviderAvailableError as e:
                yield _sse({"error": "no_provider_available", "attempts": [asdict(a) for a in e.attempts]})
                return
            except asyncio.CancelledError:
                await stream.aclose()
                if outcome.provider:
                    _used(s, call, "llm", outcome)
                raise
            _used(s, call, "llm", outcome)
            yield _sse({"done": True, "provider": outcome.provider, "model": outcome.model, "units": outcome.units})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})
