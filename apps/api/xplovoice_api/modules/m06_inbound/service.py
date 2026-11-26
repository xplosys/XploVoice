# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Inbound routing (M06). A call to one of an organisation's numbers is mapped to that organisation through a
definer function (the number is unique across all organisations), then to the number's route: an agent, an
optional queue, and a fallback for when nobody can answer.

- The organisation's phone calls are paused, or the number has no route: the caller is hung up on.
- The agent is not published: the fallback runs.
- The organisation's call limit is reached: the caller waits in the route's queue if it has one and the queue
  has room, otherwise the fallback runs. A waiting caller is connected as soon as a slot frees up, or gets the
  fallback after the queue's longest wait.
- The fallback is a short spoken message (the voice worker says it and hangs up), or an immediate hang-up."""

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from starlette.concurrency import run_in_threadpool

from ...core.config import get_settings
from ...core.db import session_scope
from ..m02_tenant.models import Tenant
from ..m04_telephony import service as tel
from ..m04_telephony.adapters import adapter
from ..m04_telephony.adapters.base import CarrierError
from ..m04_telephony.models import PhoneNumber, SipTrunk
from ..m05_agents.models import Agent, AgentVersion
from ..m05_agents.router import production_version
from ..m05_agents.schemas import AgentConfig
from ..m08_calls import dispatch, lifecycle
from ..m08_calls.models import Call
from .models import CallQueue, InboundRoute

log = logging.getLogger("xplovoice.inbound")
DEFAULT_FALLBACK = "Sorry, we can't take your call right now. Please try again later."


@dataclass
class Routed:
    result: str  # dispatched | queued | fallback | hangup | duplicate | unknown_number
    tenant_id: UUID | None = None
    call_id: UUID | None = None
    reason: str | None = None


@dataclass
class _Next:
    action: str  # dispatch | hangup | none
    tenant_id: UUID
    call_id: UUID | None
    provider: str
    room: str
    identity: str | None
    max_seconds: int


def _route_number(dialled: str) -> tuple[UUID, UUID] | None:
    with session_scope() as s:
        row = s.execute(text("select tenant_id, phone_number_id from route_inbound_number(:n)"), {"n": dialled}).first()
        return (row[0], row[1]) if row else None


def _capacity(s, tenant_id: UUID) -> bool:  # type: ignore[no-untyped-def]
    return tel.live_calls(s, tenant_id) < get_settings().max_concurrent_calls_per_tenant


def _to_agent(call: Call) -> None:
    lifecycle.enter(call, "routing", source="queue")  # first, so the session move adds no "queued" step
    lifecycle.move(call, "dispatching", source="queue")


def _fallback(call: Call, route: InboundRoute | None, reason: str) -> str:
    """Fallback for a call that already exists. Returns the action for the caller of this function."""
    if route is not None and route.fallback_action == "message":
        call.options = {
            **(call.options or {}),
            "fallback_message": route.fallback_message or DEFAULT_FALLBACK,
            "fallback_reason": reason,
        }
        _to_agent(call)
        return "dispatch"
    lifecycle.enter(call, "cancelled", source="queue", reason=reason)
    return "hangup"


def _create(
    room: str, dialled: str, caller: str | None, identity: str | None, sip_call_id: str | None, provider: str
) -> tuple[Routed, _Next | None]:
    found = _route_number(dialled)
    if not found:
        return Routed("unknown_number"), None
    tenant_id, number_id = found
    settings = get_settings()
    with session_scope(tenant_id=tenant_id) as s:
        existing = s.scalar(select(Call).where(Call.room_name == room))
        if existing is not None:  # the same caller joining twice (webhook retried): route once
            return Routed("duplicate", tenant_id, existing.id), None
        number = s.get(PhoneNumber, number_id)
        assert number is not None
        trunk = s.get(SipTrunk, number.trunk_id)
        route = s.scalar(select(InboundRoute).where(InboundRoute.phone_number_id == number.id))
        tenant = s.get(Tenant, tenant_id)
        assert tenant is not None
        pol = tel.policy_for(s, tenant_id, tenant.country_code)
        agent = s.get(Agent, route.agent_id) if route and route.status == "active" else None
        version = production_version(s, agent) if agent else None
        if version is None and agent is not None:
            # No published version: pin the latest one only to record the call; the worker never runs it.
            version = s.scalar(
                select(AgentVersion).where(AgentVersion.agent_id == agent.id).order_by(AgentVersion.version.desc())
            )
        cfg = AgentConfig.model_validate(version.config) if version else None
        if agent is None or version is None:
            # Nothing to record the call against: there is no route, so the caller is hung up on and the
            # carrier event is the only trace (a call row needs an agent).
            return Routed("hangup", tenant_id, None, "no_route"), _Next(
                "hangup", tenant_id, None, trunk.provider_key if trunk else provider, room, identity, 0
            )
        has_room = _capacity(s, tenant_id)  # counted before this call exists
        call = Call(
            tenant_id=tenant_id,
            agent_id=agent.id,
            agent_version_id=version.id,
            channel="sip",
            direction="inbound",
            status="created",
            state="initiated",
            room_name=room,
            correlation_id=secrets.token_hex(16),
            language=cfg.language if cfg else None,
            from_number=caller,
            to_number=number.e164,
            trunk_id=number.trunk_id,
            phone_number_id=number.id,
        )
        s.add(call)
        s.flush()
        prov = trunk.provider_key if trunk else provider
        tel.add_ref(s, call, prov, "room", room)
        if identity:
            tel.add_ref(s, call, prov, "participant", identity)
        if sip_call_id:
            tel.add_ref(s, call, prov, "sip_call_id", sip_call_id)
        max_seconds = min(cfg.limits.max_call_seconds if cfg else 300, settings.max_call_seconds)
        nxt = _Next("none", tenant_id, call.id, prov, room, identity, max_seconds)

        if not settings.telephony_enabled or not pol.telephony_enabled:
            lifecycle.enter(call, "cancelled", source="queue", reason="telephony_disabled")
            nxt.action = "hangup"
            return Routed("hangup", tenant_id, call.id, "telephony_disabled"), nxt
        if production_version(s, agent) is None:
            nxt.action = _fallback(call, route, "unavailable")
            return Routed("fallback" if nxt.action == "dispatch" else "hangup", tenant_id, call.id, "unavailable"), nxt
        if has_room:
            _to_agent(call)
            nxt.action = "dispatch"
            return Routed("dispatched", tenant_id, call.id), nxt
        queue = s.get(CallQueue, route.queue_id) if route.queue_id else None
        if queue is not None:
            waiting = (
                s.scalar(
                    select(func.count()).select_from(Call).where(Call.queue_id == queue.id, Call.state == "queued")
                )
                or 0
            )
            if waiting < queue.max_waiting:
                call.queue_id, call.queued_at = queue.id, datetime.now(UTC)
                lifecycle.move(call, "queued", source="queue")
                return Routed("queued", tenant_id, call.id), nxt
        nxt.action = _fallback(call, route, "unavailable")
        return Routed("fallback" if nxt.action == "dispatch" else "hangup", tenant_id, call.id, "busy_everywhere"), nxt


async def _carry_out(nxt: _Next | None) -> None:
    if nxt is None or nxt.action == "none":
        return
    if nxt.action == "dispatch" and nxt.call_id is not None:
        try:
            await run_in_threadpool(
                dispatch.enqueue, tenant_id=nxt.tenant_id, call_id=nxt.call_id, max_seconds=nxt.max_seconds
            )
            return
        except Exception:  # noqa: BLE001 - no worker reachable: the caller is hung up on, not left in silence
            log.exception("could not dispatch inbound call %s", nxt.call_id)
            await run_in_threadpool(_end, nxt.tenant_id, nxt.call_id, "failed", "no_provider")
    try:
        await adapter(nxt.provider).hangup(room=nxt.room, participant_identity=nxt.identity)
    except CarrierError as e:
        log.warning("inbound hangup failed: %s", e)


def _end(tenant_id: UUID, call_id: UUID, state: str, reason: str) -> None:
    with session_scope(tenant_id=tenant_id) as s:
        call = s.scalar(select(Call).where(Call.id == call_id).with_for_update())
        if call is not None and lifecycle.enter(call, state, source="queue", reason=reason):
            tel.finalize(s, call)


async def route_inbound(
    *,
    room: str,
    dialled: str,
    caller: str | None,
    provider: str,
    participant_identity: str | None = None,
    sip_call_id: str | None = None,
) -> Routed:
    """A caller reached one of the organisation's numbers (they are already in the room)."""
    routed, nxt = await run_in_threadpool(_create, room, dialled, caller, participant_identity, sip_call_id, provider)
    await _carry_out(nxt)
    return routed


# ------------------------------------------------------------------ the queue
def _due() -> list[tuple[UUID, UUID]]:
    with session_scope() as s:
        return [(r[0], r[1]) for r in s.execute(text("select id, tenant_id from due_queued_calls(:n)"), {"n": 50})]


def _advance(call_id: UUID, tenant_id: UUID) -> _Next | None:
    settings = get_settings()
    with session_scope(tenant_id=tenant_id) as s:
        call = s.scalar(select(Call).where(Call.id == call_id).with_for_update(skip_locked=True))
        if call is None or call.state != "queued":
            return None
        queue = s.get(CallQueue, call.queue_id) if call.queue_id else None
        route = s.scalar(select(InboundRoute).where(InboundRoute.phone_number_id == call.phone_number_id))
        version_cfg = None
        v = s.get(AgentVersion, call.agent_version_id)
        if v is not None:
            version_cfg = AgentConfig.model_validate(v.config)
        max_seconds = min(version_cfg.limits.max_call_seconds if version_cfg else 300, settings.max_call_seconds)
        provider = tel.trunk_provider(s, call)
        identity = tel.ref_for(s, call, "participant")
        nxt = _Next("none", tenant_id, call.id, provider, call.room_name, identity, max_seconds)
        # Oldest first: a caller is connected only when nobody in the same queue has waited longer.
        older = (
            s.scalar(
                select(func.count())
                .select_from(Call)
                .where(Call.queue_id == call.queue_id, Call.state == "queued", Call.queued_at < call.queued_at)
            )
            or 0
        )
        if not older and _capacity(s, tenant_id):
            _to_agent(call)
            nxt.action = "dispatch"
            return nxt
        waited = (datetime.now(UTC) - (call.queued_at or call.created_at)).total_seconds()
        if queue is None or waited >= queue.max_wait_seconds:
            nxt.action = _fallback(call, route, "queue_timeout")
            if nxt.action == "hangup":
                tel.finalize(s, call)
            return nxt
        return None


async def queue_tick() -> int:
    """Connects or times out waiting callers. Returns how many calls moved."""
    moved = 0
    for call_id, tenant_id in await run_in_threadpool(_due):
        try:
            nxt = await run_in_threadpool(_advance, call_id, tenant_id)
        except Exception:  # noqa: BLE001 - one bad call must not stop the queue
            log.exception("queue step for call %s failed", call_id)
            continue
        if nxt is not None:
            moved += 1
            await _carry_out(nxt)
    return moved
