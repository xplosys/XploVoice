# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Telephony API (M04, M06): carriers, SIP trunks, phone numbers and their inbound routes, call queues, and the
organisation's destination policy (allowed countries, premium numbers, caps, and the kill switch that pauses all
phone calls). Trunk passwords are encrypted at rest and never returned."""

import secrets
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ...core.config import get_settings
from ...core.context import Ctx, require
from ...core.errors import ApiError, bad_request, conflict, not_found
from ...core.permissions import Perm
from ...core.security import encrypt_secret
from ..m05_agents.models import Agent
from ..m06_inbound.models import CallQueue, InboundRoute
from ..m06_inbound.service import DEFAULT_FALLBACK, route_inbound
from ..m08_calls.models import Call
from ..m15_usage import billing
from . import service as tel
from .adapters import simulated
from .models import PhoneNumber, SipTrunk, TelephonyProvider

router = APIRouter(tags=["telephony"])


# ---------------------------------------------------------------------------------------------------- carriers
class ProviderOut(BaseModel):
    key: str
    name: str
    kind: str
    status: str
    description: str
    capabilities: dict
    note: str | None


@router.get("/v1/telephony/providers", response_model=list[ProviderOut])
def providers(ctx: Ctx = Depends(require(Perm.TELEPHONY_READ))) -> list[ProviderOut]:
    rows = ctx.session.scalars(select(TelephonyProvider).order_by(TelephonyProvider.key))
    out = [ProviderOut.model_validate(p, from_attributes=True) for p in rows]
    if get_settings().is_production_like:
        out = [p for p in out if p.status != "development_only"]
    return out


# ---------------------------------------------------------------------------------------------------- trunks
class TrunkIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider_key: Literal["sip", "simulated"] = "sip"
    direction: Literal["inbound", "outbound", "both"] = "both"
    address: str | None = Field(default=None, max_length=255)
    transport: Literal["udp", "tcp", "tls"] = "udp"
    auth_username: str | None = Field(default=None, max_length=120)
    auth_password: str | None = Field(default=None, max_length=200)
    allowed_addresses: list[str] = Field(default_factory=list, max_length=20)
    billing_pulse_seconds: int = Field(default=60, ge=1, le=60)


class TrunkPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    transport: Literal["udp", "tcp", "tls"] | None = None
    auth_username: str | None = Field(default=None, max_length=120)
    auth_password: str | None = Field(default=None, max_length=200)  # empty string clears it
    allowed_addresses: list[str] | None = Field(default=None, max_length=20)
    billing_pulse_seconds: int | None = Field(default=None, ge=1, le=60)
    status: Literal["active", "disabled"] | None = None


class TrunkOut(BaseModel):
    id: UUID
    name: str
    provider_key: str
    direction: str
    address: str | None
    transport: str
    auth_username: str | None
    has_password: bool
    allowed_addresses: list[str]
    billing_pulse_seconds: int
    status: str
    sync_status: str
    sync_error: str | None
    numbers: int
    created_at: datetime
    updated_at: datetime


def _trunk(ctx: Ctx, trunk_id: UUID) -> SipTrunk:
    t = ctx.session.scalar(select(SipTrunk).where(SipTrunk.id == trunk_id, SipTrunk.tenant_id == ctx.tenant.id))
    if not t:
        raise not_found()
    return t


def _trunk_out(ctx: Ctx, t: SipTrunk) -> TrunkOut:
    n = ctx.session.scalar(
        select(func.count())
        .select_from(PhoneNumber)
        .where(PhoneNumber.trunk_id == t.id, PhoneNumber.status == "active")
    )
    return TrunkOut(
        id=t.id,
        name=t.name,
        provider_key=t.provider_key,
        direction=t.direction,
        address=t.address,
        transport=t.transport,
        auth_username=t.auth_username,
        has_password=bool(t.auth_secret_ciphertext),
        allowed_addresses=list(t.allowed_addresses or []),
        billing_pulse_seconds=int((t.capabilities or {}).get("billing_pulse_seconds") or 60),
        status=t.status,
        sync_status=t.sync_status,
        sync_error=t.sync_error,
        numbers=n or 0,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def _provider_ok(key: str) -> None:
    if key == "simulated" and get_settings().is_production_like:
        raise bad_request("provider_unavailable", "The simulated carrier is for development and tests only.")


@router.get("/v1/telephony/trunks", response_model=list[TrunkOut])
def list_trunks(ctx: Ctx = Depends(require(Perm.TELEPHONY_READ))) -> list[TrunkOut]:
    return [_trunk_out(ctx, t) for t in ctx.session.scalars(select(SipTrunk).order_by(SipTrunk.created_at))]


@router.post("/v1/telephony/trunks", response_model=TrunkOut, status_code=status.HTTP_201_CREATED)
async def create_trunk(data: TrunkIn, ctx: Ctx = Depends(require(Perm.TELEPHONY_MANAGE))) -> TrunkOut:
    _provider_ok(data.provider_key)
    if data.provider_key == "sip" and data.direction != "inbound" and not data.address:
        raise bad_request("address_required", "Enter your carrier's SIP address to place outbound calls.")
    t = SipTrunk(
        tenant_id=ctx.tenant.id,
        name=data.name.strip(),
        provider_key=data.provider_key,
        direction=data.direction,
        address=(data.address or "").strip() or None,
        transport=data.transport,
        auth_username=data.auth_username or None,
        auth_secret_ciphertext=encrypt_secret(data.auth_password) if data.auth_password else None,
        allowed_addresses=[a.strip() for a in data.allowed_addresses if a.strip()],
        capabilities={"billing_pulse_seconds": data.billing_pulse_seconds},
        created_by_membership_id=ctx.membership.id,
    )
    ctx.session.add(t)
    ctx.session.flush()
    ctx.audit("telephony.trunk_created", resource_type="sip_trunk", resource_id=str(t.id), provider=t.provider_key)
    ctx.commit()
    synced = await tel.sync_trunk(ctx.tenant.id, t.id)
    ctx.session.refresh(t)
    t.sync_status = synced.sync_status
    return _trunk_out(ctx, t)


@router.patch("/v1/telephony/trunks/{trunk_id}", response_model=TrunkOut)
async def update_trunk(
    trunk_id: UUID, data: TrunkPatch, ctx: Ctx = Depends(require(Perm.TELEPHONY_MANAGE))
) -> TrunkOut:
    t = _trunk(ctx, trunk_id)
    fields = data.model_dump(exclude_unset=True)
    for k in ("name", "address", "transport", "auth_username", "status"):
        if k in fields:
            setattr(t, k, fields[k].strip() if isinstance(fields[k], str) else fields[k])
    if "allowed_addresses" in fields and data.allowed_addresses is not None:
        t.allowed_addresses = [a.strip() for a in data.allowed_addresses if a.strip()]
    if "auth_password" in fields:
        t.auth_secret_ciphertext = encrypt_secret(data.auth_password) if data.auth_password else None
    if data.billing_pulse_seconds is not None:
        t.capabilities = {**(t.capabilities or {}), "billing_pulse_seconds": data.billing_pulse_seconds}
    t.sync_status, t.updated_at = "pending", datetime.now(UTC)
    ctx.audit(
        "telephony.trunk_updated",
        resource_type="sip_trunk",
        resource_id=str(t.id),
        fields=sorted(k for k in fields if k != "auth_password") + (["password"] if "auth_password" in fields else []),
    )
    ctx.commit()
    await tel.sync_trunk(ctx.tenant.id, t.id)
    ctx.session.refresh(t)
    return _trunk_out(ctx, t)


@router.post("/v1/telephony/trunks/{trunk_id}/sync", response_model=TrunkOut)
async def sync_trunk(trunk_id: UUID, ctx: Ctx = Depends(require(Perm.TELEPHONY_MANAGE))) -> TrunkOut:
    t = _trunk(ctx, trunk_id)
    ctx.commit()
    await tel.sync_trunk(ctx.tenant.id, t.id)
    ctx.session.refresh(t)
    ctx.audit("telephony.trunk_synced", resource_type="sip_trunk", resource_id=str(t.id), result_status=t.sync_status)
    return _trunk_out(ctx, t)


# ---------------------------------------------------------------------------------------------------- numbers
class RouteIn(BaseModel):
    agent_id: UUID
    queue_id: UUID | None = None
    fallback_action: Literal["message", "hangup"] = "message"
    fallback_message: str = Field(default=DEFAULT_FALLBACK, min_length=1, max_length=300)
    status: Literal["active", "disabled"] = "active"


class RouteOut(BaseModel):
    agent_id: UUID
    agent_name: str
    agent_status: str
    queue_id: UUID | None
    fallback_action: str
    fallback_message: str
    status: str


class NumberIn(BaseModel):
    number: str = Field(min_length=4, max_length=30)
    trunk_id: UUID
    label: str = Field(default="", max_length=120)
    inbound: bool = True
    outbound: bool = True


class NumberPatch(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    inbound: bool | None = None
    outbound: bool | None = None


class NumberOut(BaseModel):
    id: UUID
    e164: str
    country_code: str
    trunk_id: UUID
    trunk_name: str
    provider_key: str
    label: str
    inbound: bool
    outbound: bool
    status: str
    route: RouteOut | None
    created_at: datetime


def _number(ctx: Ctx, number_id: UUID) -> PhoneNumber:
    n = ctx.session.scalar(
        select(PhoneNumber).where(PhoneNumber.id == number_id, PhoneNumber.tenant_id == ctx.tenant.id)
    )
    if not n:
        raise not_found()
    return n


def _number_out(ctx: Ctx, n: PhoneNumber) -> NumberOut:
    t = ctx.session.get(SipTrunk, n.trunk_id)
    r = ctx.session.scalar(select(InboundRoute).where(InboundRoute.phone_number_id == n.id))
    route = None
    if r is not None:
        a = ctx.session.get(Agent, r.agent_id)
        route = RouteOut(
            agent_id=r.agent_id,
            agent_name=a.name if a else "",
            agent_status=a.status if a else "",
            queue_id=r.queue_id,
            fallback_action=r.fallback_action,
            fallback_message=r.fallback_message,
            status=r.status,
        )
    return NumberOut(
        id=n.id,
        e164=n.e164,
        country_code=n.country_code,
        trunk_id=n.trunk_id,
        trunk_name=t.name if t else "",
        provider_key=t.provider_key if t else "",
        label=n.label,
        inbound=n.inbound,
        outbound=n.outbound,
        status=n.status,
        route=route,
        created_at=n.created_at,
    )


@router.get("/v1/phone-numbers", response_model=list[NumberOut])
def list_numbers(ctx: Ctx = Depends(require(Perm.TELEPHONY_READ))) -> list[NumberOut]:
    q = select(PhoneNumber).order_by(PhoneNumber.status, PhoneNumber.created_at)
    return [_number_out(ctx, n) for n in ctx.session.scalars(q)]


@router.post("/v1/phone-numbers", response_model=NumberOut, status_code=status.HTTP_201_CREATED)
async def add_number(data: NumberIn, ctx: Ctx = Depends(require(Perm.TELEPHONY_MANAGE))) -> NumberOut:
    """Adds a number the organisation already has from its carrier, reached through one of its trunks."""
    t = _trunk(ctx, data.trunk_id)
    if t.status != "active":
        raise bad_request("trunk_disabled", "That trunk is disabled.")
    try:
        e164, country = tel.e164(data.number, ctx.tenant.country_code)
    except tel.TelephonyError as e:
        raise bad_request(e.code, e.message) from None
    limit = billing.plan_limit(ctx.session, "max_phone_numbers")
    if limit is not None:
        held = ctx.session.scalar(select(func.count()).select_from(PhoneNumber).where(PhoneNumber.status == "active"))
        if (held or 0) >= limit:
            raise ApiError(402, "plan_limit", f"Your plan allows {limit} phone numbers. Release one or change plan.")
    n = PhoneNumber(
        tenant_id=ctx.tenant.id,
        e164=e164,
        country_code=country,
        trunk_id=t.id,
        label=data.label.strip(),
        inbound=data.inbound,
        outbound=data.outbound,
    )
    ctx.session.add(n)
    try:
        ctx.session.flush()
    except IntegrityError:
        ctx.session.rollback()
        # The number is unique across all organisations; never say which one has it.
        raise conflict("number_in_use", "That number is already in use.") from None
    ctx.audit("telephony.number_added", resource_type="phone_number", resource_id=str(n.id), country=country)
    ctx.commit()
    await tel.sync_trunk(ctx.tenant.id, t.id)  # the carrier-side inbound trunk lists the numbers it answers
    return _number_out(ctx, n)


@router.patch("/v1/phone-numbers/{number_id}", response_model=NumberOut)
def update_number(number_id: UUID, data: NumberPatch, ctx: Ctx = Depends(require(Perm.TELEPHONY_MANAGE))) -> NumberOut:
    n = _number(ctx, number_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(n, k, v.strip() if isinstance(v, str) else v)
    ctx.audit("telephony.number_updated", resource_type="phone_number", resource_id=str(n.id))
    return _number_out(ctx, n)


@router.post("/v1/phone-numbers/{number_id}/release", response_model=NumberOut)
async def release_number(number_id: UUID, ctx: Ctx = Depends(require(Perm.TELEPHONY_MANAGE))) -> NumberOut:
    """Stops using a number. Its history (calls, campaigns) is kept; the number can be added again later."""
    from ..m07_campaigns.models import Campaign

    n = _number(ctx, number_id)
    if n.status == "released":
        return _number_out(ctx, n)
    busy = ctx.session.scalar(
        select(Campaign.id).where(Campaign.from_number_id == n.id, Campaign.status.in_(("running", "approved")))
    )
    if busy:
        raise conflict("number_in_use", "A running or approved campaign calls from this number. Pause it first.")
    n.status = "released"
    r = ctx.session.scalar(select(InboundRoute).where(InboundRoute.phone_number_id == n.id))
    if r is not None:
        r.status = "disabled"
    ctx.audit("telephony.number_released", resource_type="phone_number", resource_id=str(n.id))
    ctx.commit()
    await tel.sync_trunk(ctx.tenant.id, n.trunk_id)
    return _number_out(ctx, n)


@router.put("/v1/phone-numbers/{number_id}/route", response_model=NumberOut)
def set_route(number_id: UUID, data: RouteIn, ctx: Ctx = Depends(require(Perm.TELEPHONY_MANAGE))) -> NumberOut:
    n = _number(ctx, number_id)
    if n.status != "active":
        raise bad_request("number_released", "That number has been released.")
    agent = ctx.session.scalar(select(Agent).where(Agent.id == data.agent_id, Agent.tenant_id == ctx.tenant.id))
    if not agent or agent.status == "archived":
        raise bad_request("agent_not_found", "Choose one of your agents.")
    if data.queue_id and not ctx.session.scalar(
        select(CallQueue.id).where(CallQueue.id == data.queue_id, CallQueue.tenant_id == ctx.tenant.id)
    ):
        raise bad_request("queue_not_found", "Choose one of your queues.")
    r = ctx.session.scalar(select(InboundRoute).where(InboundRoute.phone_number_id == n.id))
    if r is None:
        r = InboundRoute(tenant_id=ctx.tenant.id, phone_number_id=n.id, agent_id=agent.id, fallback_message="")
        ctx.session.add(r)
    r.agent_id, r.queue_id = agent.id, data.queue_id
    r.fallback_action, r.fallback_message = data.fallback_action, data.fallback_message.strip()
    r.status, r.updated_at = data.status, datetime.now(UTC)
    ctx.session.flush()
    ctx.audit(
        "telephony.route_set",
        resource_type="phone_number",
        resource_id=str(n.id),
        agent=str(agent.id),
        queue=str(data.queue_id) if data.queue_id else None,
        fallback=data.fallback_action,
    )
    return _number_out(ctx, n)


@router.delete("/v1/phone-numbers/{number_id}/route", response_model=NumberOut)
def delete_route(number_id: UUID, ctx: Ctx = Depends(require(Perm.TELEPHONY_MANAGE))) -> NumberOut:
    n = _number(ctx, number_id)
    r = ctx.session.scalar(select(InboundRoute).where(InboundRoute.phone_number_id == n.id))
    if r is not None:
        ctx.session.delete(r)
        ctx.session.flush()
        ctx.audit("telephony.route_removed", resource_type="phone_number", resource_id=str(n.id))
    return _number_out(ctx, n)


# ---------------------------------------------------------------------------------------------------- queues
class QueueIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    max_waiting: int = Field(default=5, ge=1, le=50)
    max_wait_seconds: int = Field(default=60, ge=10, le=600)


class QueueOut(QueueIn):
    id: UUID
    waiting: int
    created_at: datetime


def _queue_out(ctx: Ctx, q: CallQueue) -> QueueOut:
    waiting = ctx.session.scalar(
        select(func.count()).select_from(Call).where(Call.queue_id == q.id, Call.state == "queued")
    )
    return QueueOut(
        id=q.id,
        name=q.name,
        max_waiting=q.max_waiting,
        max_wait_seconds=q.max_wait_seconds,
        waiting=waiting or 0,
        created_at=q.created_at,
    )


@router.get("/v1/queues", response_model=list[QueueOut])
def list_queues(ctx: Ctx = Depends(require(Perm.TELEPHONY_READ))) -> list[QueueOut]:
    return [_queue_out(ctx, q) for q in ctx.session.scalars(select(CallQueue).order_by(CallQueue.created_at))]


@router.post("/v1/queues", response_model=QueueOut, status_code=status.HTTP_201_CREATED)
def create_queue(data: QueueIn, ctx: Ctx = Depends(require(Perm.TELEPHONY_MANAGE))) -> QueueOut:
    q = CallQueue(
        tenant_id=ctx.tenant.id,
        name=data.name.strip(),
        max_waiting=data.max_waiting,
        max_wait_seconds=data.max_wait_seconds,
    )
    ctx.session.add(q)
    ctx.session.flush()
    ctx.session.refresh(q)
    ctx.audit("telephony.queue_created", resource_type="call_queue", resource_id=str(q.id))
    return _queue_out(ctx, q)


def _queue(ctx: Ctx, queue_id: UUID) -> CallQueue:
    q = ctx.session.scalar(select(CallQueue).where(CallQueue.id == queue_id, CallQueue.tenant_id == ctx.tenant.id))
    if not q:
        raise not_found()
    return q


@router.put("/v1/queues/{queue_id}", response_model=QueueOut)
def update_queue(queue_id: UUID, data: QueueIn, ctx: Ctx = Depends(require(Perm.TELEPHONY_MANAGE))) -> QueueOut:
    q = _queue(ctx, queue_id)
    q.name, q.max_waiting, q.max_wait_seconds = data.name.strip(), data.max_waiting, data.max_wait_seconds
    ctx.audit("telephony.queue_updated", resource_type="call_queue", resource_id=str(q.id))
    return _queue_out(ctx, q)


@router.delete("/v1/queues/{queue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_queue(queue_id: UUID, ctx: Ctx = Depends(require(Perm.TELEPHONY_MANAGE))) -> None:
    q = _queue(ctx, queue_id)
    if ctx.session.scalar(select(InboundRoute.id).where(InboundRoute.queue_id == q.id)):
        raise conflict("queue_in_use", "A number's route uses this queue. Change the route first.")
    if ctx.session.scalar(select(Call.id).where(Call.queue_id == q.id).limit(1)):
        raise conflict("queue_has_calls", "Calls have waited in this queue, so it is kept for their history.")
    ctx.session.delete(q)
    ctx.audit("telephony.queue_deleted", resource_type="call_queue", resource_id=str(queue_id))


# ---------------------------------------------------------------------------------------------------- policy
class PolicyIn(BaseModel):
    telephony_enabled: bool
    allowed_countries: list[str] = Field(min_length=1, max_length=50)
    block_premium: bool = True
    max_concurrent_outbound: int = Field(ge=1, le=50)
    daily_outbound_minutes: int = Field(ge=1, le=100000)


class PolicyOut(PolicyIn):
    platform_enabled: bool
    live_outbound: int
    outbound_minutes_today: int
    updated_at: datetime


def _policy_out(ctx: Ctx) -> PolicyOut:
    from .models import TelephonyUsage

    p = tel.policy_for(ctx.session, ctx.tenant.id, ctx.tenant.country_code)
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    used = (
        ctx.session.scalar(
            select(func.coalesce(func.sum(TelephonyUsage.billed_seconds), 0)).where(
                TelephonyUsage.direction == "outbound", TelephonyUsage.created_at >= day_start
            )
        )
        or 0
    )
    return PolicyOut(
        telephony_enabled=p.telephony_enabled,
        allowed_countries=list(p.allowed_countries),
        block_premium=p.block_premium,
        max_concurrent_outbound=p.max_concurrent_outbound,
        daily_outbound_minutes=p.daily_outbound_minutes,
        platform_enabled=get_settings().telephony_enabled,
        live_outbound=tel.live_outbound(ctx.session, ctx.tenant.id),
        outbound_minutes_today=int(used) // 60,
        updated_at=p.updated_at,
    )


@router.get("/v1/destination-policy", response_model=PolicyOut)
def read_policy(ctx: Ctx = Depends(require(Perm.TELEPHONY_READ))) -> PolicyOut:
    return _policy_out(ctx)


@router.put("/v1/destination-policy", response_model=PolicyOut)
def update_policy(data: PolicyIn, ctx: Ctx = Depends(require(Perm.TELEPHONY_MANAGE))) -> PolicyOut:
    countries = sorted({c.strip().upper() for c in data.allowed_countries})
    if any(len(c) != 2 or not c.isalpha() for c in countries):
        raise bad_request("invalid_country", "Use two-letter country codes, such as IN or US.")
    p = tel.policy_for(ctx.session, ctx.tenant.id, ctx.tenant.country_code)
    before = {
        "telephony_enabled": p.telephony_enabled,
        "allowed_countries": list(p.allowed_countries),
        "block_premium": p.block_premium,
        "max_concurrent_outbound": p.max_concurrent_outbound,
        "daily_outbound_minutes": p.daily_outbound_minutes,
    }
    p.telephony_enabled, p.allowed_countries, p.block_premium = data.telephony_enabled, countries, data.block_premium
    p.max_concurrent_outbound, p.daily_outbound_minutes = data.max_concurrent_outbound, data.daily_outbound_minutes
    p.updated_by_membership_id, p.updated_at = ctx.membership.id, datetime.now(UTC)
    after = {**data.model_dump(), "allowed_countries": countries}
    changed = {k: {"from": before[k], "to": after[k]} for k in before if before[k] != after[k]}
    if "telephony_enabled" in changed:
        ctx.audit(
            "telephony.paused" if not data.telephony_enabled else "telephony.resumed",
            resource_type="destination_policy",
            resource_id=str(ctx.tenant.id),
        )
    ctx.audit(
        "telephony.policy_updated", resource_type="destination_policy", resource_id=str(ctx.tenant.id), changes=changed
    )
    ctx.session.flush()
    return _policy_out(ctx)


# ---------------------------------------------------------------------------------------------------- dev only
class SimInboundIn(BaseModel):
    to: str = Field(min_length=4, max_length=30)
    caller: str = Field(default="+919800000001", min_length=4, max_length=30)


class SimInboundOut(BaseModel):
    result: str
    call_id: UUID | None
    reason: str | None


def _dev_only() -> None:
    if get_settings().is_production_like:
        raise not_found()


@router.post("/v1/telephony/simulate/inbound", response_model=SimInboundOut)
async def simulate_inbound(data: SimInboundIn, ctx: Ctx = Depends(require(Perm.TELEPHONY_MANAGE))) -> SimInboundOut:
    """Development only: a phone call to one of your numbers on a simulated trunk, routed exactly as a real one."""
    _dev_only()
    try:
        to, _ = tel.e164(data.to, ctx.tenant.country_code)
        caller, _ = tel.e164(data.caller, ctx.tenant.country_code)
    except tel.TelephonyError as e:
        raise bad_request(e.code, e.message) from None
    n = ctx.session.scalar(select(PhoneNumber).where(PhoneNumber.e164 == to, PhoneNumber.status == "active"))
    t = ctx.session.get(SipTrunk, n.trunk_id) if n else None
    if not n or not t or t.provider_key != "simulated":
        raise bad_request("not_simulated", "Choose one of your numbers on a simulated trunk.")
    ctx.audit("telephony.simulated_inbound", resource_type="phone_number", resource_id=str(n.id))
    ctx.commit()
    room = f"xvin_{secrets.token_urlsafe(18)}"
    routed = await route_inbound(
        room=room, dialled=to, caller=caller, provider="simulated", participant_identity=f"sim-{secrets.token_hex(6)}"
    )
    if routed.call_id and routed.tenant_id:
        from ...core.db import session_scope

        with session_scope(tenant_id=routed.tenant_id) as s:
            call = s.get(Call, routed.call_id)
            if call is not None:
                tel.add_ref(s, call, "simulated", "call", f"simcall_{call.id}")
    return SimInboundOut(result=routed.result, call_id=routed.call_id, reason=routed.reason)


class SimEventIn(BaseModel):
    status: Literal["in_progress", "completed", "disconnected", "busy", "no_answer", "failed", "cancelled"]
    event_id: str | None = Field(default=None, max_length=100)


@router.post("/v1/telephony/simulate/calls/{call_id}/event")
async def simulate_event(call_id: UUID, data: SimEventIn, ctx: Ctx = Depends(require(Perm.TELEPHONY_MANAGE))) -> dict:
    """Development only: the simulated carrier reports a status change, through the same verified ingest path."""
    import json

    from starlette.concurrency import run_in_threadpool

    _dev_only()
    call = ctx.session.scalar(select(Call).where(Call.id == call_id, Call.tenant_id == ctx.tenant.id))
    if not call or tel.trunk_provider(ctx.session, call) != "simulated":
        raise not_found()
    ref = tel.ref_for(ctx.session, call, "call") or f"simcall_{call.id}"
    ctx.commit()
    body = simulated.event(ref, data.status)
    ev = json.loads(body)
    if data.event_id:
        ev["id"] = data.event_id
    result, _, _ = await run_in_threadpool(
        tel.ingest,
        tel.CarrierEvent(
            provider="simulated",
            event_id=ev["id"],
            type="status",
            state=data.status,
            occurred_at=datetime.now(UTC),
            ref_kind="call",
            ref=ref,
            reason={"failed": "carrier_failed"}.get(data.status, "caller_hangup"),
        ),
    )
    return {"result": result}
