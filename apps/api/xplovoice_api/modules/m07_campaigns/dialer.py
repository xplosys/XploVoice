# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Campaign dialer (M07). Runs inside each API process. Due contacts are listed through a definer function and
then claimed one by one under their own tenant with SKIP LOCKED, so several processes can run it safely.

For each contact: the policy engine decides (stored with every check), and only an allowed call reaches the
carrier. The call is created in the call's tenant, a voice worker is dispatched to its room, and the carrier
adapter dials. The carrier's answer (answered, busy, no answer, failed) moves the call through the lifecycle and
the contact through the retry policy."""

import asyncio
import contextlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text
from starlette.concurrency import run_in_threadpool

from ...core.config import get_settings
from ...core.db import session_scope
from ..m02_tenant.models import Tenant
from ..m04_telephony import service as tel
from ..m04_telephony.adapters import adapter
from ..m04_telephony.adapters.base import CarrierError, PlaceRequest, PlaceResult
from ..m04_telephony.models import PhoneNumber, SipTrunk
from ..m05_agents.models import Agent
from ..m05_agents.router import production_version
from ..m05_agents.schemas import AgentConfig
from ..m08_calls import dispatch, lifecycle
from ..m08_calls.models import Call
from . import policy
from .models import Campaign, CampaignContact, DialAttempt
from .service import maybe_complete

log = logging.getLogger("xplovoice.dialer")


@dataclass
class Plan:
    tenant_id: UUID
    call_id: UUID
    provider: str
    request: PlaceRequest
    max_seconds: int


def _plan(contact_id: UUID, tenant_id: UUID) -> Plan | None:
    settings = get_settings()
    with session_scope(tenant_id=tenant_id) as s:
        contact = s.scalar(
            select(CampaignContact).where(CampaignContact.id == contact_id).with_for_update(skip_locked=True)
        )
        if not contact or contact.status not in ("pending", "retry") or contact.next_attempt_at > datetime.now(UTC):
            return None
        campaign = s.get(Campaign, contact.campaign_id)
        tenant = s.get(Tenant, tenant_id)
        assert campaign and tenant
        pol = tel.policy_for(s, tenant_id, tenant.country_code)
        d = policy.evaluate_outbound(s, pol, campaign, contact)
        now = datetime.now(UTC)
        number = s.get(PhoneNumber, campaign.from_number_id)
        trunk = s.get(SipTrunk, number.trunk_id) if number else None
        agent = s.get(Agent, campaign.agent_id)
        version = production_version(s, agent) if agent else None
        if d.allowed and (not number or number.status != "active" or not trunk or trunk.status != "active"):
            d = policy.Decision("block", "from_number_unavailable", [*d.checks, policy.Check("from_number", False)])
        if d.allowed and version is None:
            d = policy.Decision(
                "defer",
                "agent_not_published",
                [*d.checks, policy.Check("agent_published", False)],
                now + timedelta(minutes=15),
            )
        policy.record(
            s,
            d,
            tenant_id=tenant_id,
            phone=contact.phone,
            purpose="outbound_call",
            campaign_id=campaign.id,
            contact_id=contact.id,
        )
        if d.decision == "block":
            contact.status = "exhausted" if d.reason == "attempts_used" else "blocked"
            contact.block_reason, contact.updated_at = d.reason, now
            maybe_complete(s, campaign)
            return None
        if d.decision == "defer":
            if d.retry_at is None:  # the window never opens in the next 8 days (e.g. no calling days)
                contact.status, contact.block_reason = "blocked", "calling_window"
            else:
                contact.next_attempt_at = d.retry_at
            contact.updated_at = now
            return None
        assert number and trunk and version and agent
        cfg = AgentConfig.model_validate(version.config)
        call = Call(
            tenant_id=tenant_id,
            agent_id=agent.id,
            agent_version_id=version.id,
            channel="sip",
            direction="outbound",
            status="created",
            state="initiated",
            room_name=f"xvout_{secrets.token_urlsafe(18)}",
            correlation_id=secrets.token_hex(16),
            language=cfg.language,
            from_number=number.e164,
            to_number=contact.phone,
            trunk_id=trunk.id,
            phone_number_id=number.id,
            campaign_id=campaign.id,
        )
        s.add(call)
        s.flush()
        lifecycle.enter(call, "queued", source="dialer")
        contact.attempts += 1
        contact.status, contact.last_call_id, contact.updated_at = "calling", call.id, now
        s.add(
            DialAttempt(
                tenant_id=tenant_id,
                campaign_id=campaign.id,
                contact_id=contact.id,
                call_id=call.id,
                attempt_no=contact.attempts,
            )
        )
        identity = f"phone-{call.id.hex[:12]}"
        tel.add_ref(s, call, trunk.provider_key, "participant", identity)
        return Plan(
            tenant_id=tenant_id,
            call_id=call.id,
            provider=trunk.provider_key,
            max_seconds=min(cfg.limits.max_call_seconds, settings.max_call_seconds),
            request=PlaceRequest(
                call_id=str(call.id),
                room=call.room_name,
                participant_identity=identity,
                to_e164=contact.phone,
                from_e164=number.e164,
                outbound_trunk_id=trunk.livekit_outbound_trunk_id,
                ring_timeout_seconds=settings.ring_timeout_seconds,
            ),
        )


def _apply(plan: Plan, result: PlaceResult) -> None:
    with session_scope(tenant_id=plan.tenant_id) as s:
        call = s.scalar(select(Call).where(Call.id == plan.call_id).with_for_update())
        assert call is not None
        for kind, ref in result.refs:
            tel.add_ref(s, call, plan.provider, kind, ref)
        attempt = s.scalar(select(DialAttempt).where(DialAttempt.call_id == call.id))
        if attempt is not None:
            attempt.sip_status = result.sip_status
        if result.outcome == "answered":
            lifecycle.enter(call, "answered", source="carrier")
            lifecycle.enter(call, "connected", source="carrier")
        else:
            reason = "carrier_failed" if result.outcome == "failed" else result.outcome
            if lifecycle.enter(call, result.outcome, source="carrier", reason=reason):
                tel.finalize(s, call)


async def place(plan: Plan) -> str:
    try:
        await run_in_threadpool(
            dispatch.enqueue, tenant_id=plan.tenant_id, call_id=plan.call_id, max_seconds=plan.max_seconds
        )
        await run_in_threadpool(_dispatching, plan)
    except Exception:  # noqa: BLE001 - no worker: the call fails before anyone is dialled
        log.exception("could not dispatch outbound call %s", plan.call_id)
        await run_in_threadpool(_apply, plan, PlaceResult(outcome="failed", detail="No voice worker"))
        return "failed"
    try:
        result = await adapter(plan.provider).place_call(plan.request)
    except CarrierError as e:
        result = PlaceResult(outcome="failed", detail=str(e))
    await run_in_threadpool(_apply, plan, result)
    return result.outcome


def _dispatching(plan: Plan) -> None:
    with session_scope(tenant_id=plan.tenant_id) as s:
        call = s.get(Call, plan.call_id)
        assert call is not None
        lifecycle.move(call, "dispatching", source="dialer")
        lifecycle.enter(call, "ringing", source="dialer")


def _due(limit: int) -> list[tuple[UUID, UUID]]:
    with session_scope() as s:
        return [
            (r[0], r[1]) for r in s.execute(text("select id, tenant_id from due_campaign_contacts(:n)"), {"n": limit})
        ]


async def tick(limit: int = 20) -> list[asyncio.Task[str]]:
    """One pass. Returns the dialling tasks (tests await them; the loop lets them run)."""
    tasks: list[asyncio.Task[str]] = []
    for contact_id, tenant_id in await run_in_threadpool(_due, limit):
        try:
            plan = await run_in_threadpool(_plan, contact_id, tenant_id)
        except Exception:  # noqa: BLE001 - one bad contact must not stop the others
            log.exception("planning contact %s failed", contact_id)
            continue
        if plan:
            tasks.append(asyncio.create_task(place(plan)))
    return tasks


async def loop(interval: float = 5.0) -> None:
    from ..m06_inbound import service as inbound

    while True:
        with contextlib.suppress(Exception):
            await tick()
        with contextlib.suppress(Exception):
            await inbound.queue_tick()
        await asyncio.sleep(interval)
