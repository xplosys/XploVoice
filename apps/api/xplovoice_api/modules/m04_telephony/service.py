# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Telephony service (M04): numbers, trunks, carrier references, carrier events and the end-of-call hooks.

Carrier events are verified by the webhook layer, then stored once per carrier event id before they may change
a call, so a duplicated, delayed or out-of-order event is harmless (CR-003). The state machine decides whether
an event still applies; the event is kept either way, marked applied or not."""

import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import phonenumbers
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ...core.db import session_scope
from ...core.security import decrypt_secret
from ..m08_calls import lifecycle
from ..m08_calls.models import Call
from .adapters import adapter
from .adapters.base import CarrierError, TrunkSpec
from .models import CallProviderEvent, CallProviderRef, DestinationPolicy, PhoneNumber, SipTrunk, TelephonyUsage

log = logging.getLogger("xplovoice.telephony")
DEFAULT_PULSE_SECONDS = 60


class TelephonyError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def e164(value: str, default_country: str) -> tuple[str, str]:
    """Normalises a phone number. Returns (E.164, ISO country)."""
    try:
        n = phonenumbers.parse(value.strip(), default_country)
    except phonenumbers.NumberParseException:
        raise TelephonyError("invalid_phone", f"{value[:40]} isn't a valid phone number.") from None
    if not phonenumbers.is_valid_number(n):
        raise TelephonyError("invalid_phone", f"{value[:40]} isn't a valid phone number.")
    return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164), phonenumbers.region_code_for_number(n)


def policy_for(s: Session, tenant_id: UUID, country: str) -> DestinationPolicy:
    """The organisation's destination policy, created on first use: its own country only, premium numbers
    blocked, small concurrency and daily caps (toll-fraud defaults, HLD v1.3 section 9)."""
    p = s.get(DestinationPolicy, tenant_id)
    if p is None:
        s.execute(
            insert(DestinationPolicy).values(tenant_id=tenant_id, allowed_countries=[country]).on_conflict_do_nothing()
        )
        s.flush()
        p = s.get(DestinationPolicy, tenant_id)
    assert p is not None
    return p


def add_ref(s: Session, call: Call, provider: str, kind: str, ref: str) -> None:
    s.execute(
        insert(CallProviderRef)
        .values(tenant_id=call.tenant_id, call_id=call.id, provider_key=provider, kind=kind, ref=ref[:200])
        .on_conflict_do_nothing()
    )


def ref_for(s: Session, call: Call, kind: str) -> str | None:
    return s.scalar(
        select(CallProviderRef.ref).where(CallProviderRef.call_id == call.id, CallProviderRef.kind == kind).limit(1)
    )


def trunk_provider(s: Session, call: Call) -> str:
    if call.trunk_id:
        t = s.get(SipTrunk, call.trunk_id)
        if t:
            return t.provider_key
    return "simulated"


def live_outbound(s: Session, tenant_id: UUID) -> int:
    return (
        s.scalar(
            select(func.count())
            .select_from(Call)
            .where(
                Call.tenant_id == tenant_id,
                Call.direction == "outbound",
                Call.state.not_in(lifecycle.TERMINAL_STATES),
            )
        )
        or 0
    )


def live_calls(s: Session, tenant_id: UUID) -> int:
    """Calls using a voice worker now (queued inbound callers wait outside this count)."""
    return (
        s.scalar(
            select(func.count())
            .select_from(Call)
            .where(
                Call.tenant_id == tenant_id,
                Call.status.not_in(lifecycle.TERMINAL | {"queued"}),
                Call.channel != "chat",
            )
        )
        or 0
    )


# ------------------------------------------------------------------ carrier events
@dataclass
class CarrierEvent:
    provider: str
    event_id: str
    type: str
    state: str | None
    occurred_at: datetime
    ref_kind: str | None = None
    ref: str | None = None
    room: str | None = None
    reason: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


def find_call(ev: CarrierEvent) -> tuple[UUID, UUID] | None:
    with session_scope() as s:
        if ev.ref_kind and ev.ref:
            row = s.execute(
                text("select tenant_id, call_id from find_call_by_provider_ref(:p, :k, :r)"),
                {"p": ev.provider, "k": ev.ref_kind, "r": ev.ref},
            ).first()
            if row:
                return row[0], row[1]
        if ev.room:
            row = s.execute(text("select tenant_id, call_id from find_call_by_room(:r)"), {"r": ev.room}).first()
            if row:
                return row[0], row[1]
    return None


def ingest(ev: CarrierEvent) -> tuple[str, UUID | None, UUID | None]:
    """Returns (result, tenant, call). result: applied | ignored | duplicate | unknown_call."""
    found = find_call(ev)
    if not found:
        return "unknown_call", None, None
    tenant_id, call_id = found
    with session_scope(tenant_id=tenant_id) as s:
        row = s.execute(
            insert(CallProviderEvent)
            .values(
                tenant_id=tenant_id,
                call_id=call_id,
                provider_key=ev.provider,
                event_id=ev.event_id[:200],
                type=ev.type[:60],
                state=ev.state,
                occurred_at=ev.occurred_at,
                applied=False,
                data=ev.data,
            )
            .on_conflict_do_nothing()
            .returning(CallProviderEvent.id)
        ).first()
        if row is None:
            return "duplicate", tenant_id, call_id
        call = s.scalar(select(Call).where(Call.id == call_id).with_for_update())
        assert call is not None
        applied = False
        if ev.state:
            applied = lifecycle.enter(call, ev.state, source="carrier", reason=ev.reason or ev.state, at=ev.occurred_at)
        if applied:
            s.execute(text("update call_provider_events set applied = true where id = :id"), {"id": row[0]})
            if call.state in lifecycle.TERMINAL_STATES:
                finalize(s, call)
        ended = applied and call.state in lifecycle.TERMINAL_STATES
    if ended:
        _stop_worker(call_id)
    return ("applied" if applied else "ignored"), tenant_id, call_id


def _stop_worker(call_id: UUID) -> None:
    from ..m08_calls import dispatch

    try:
        dispatch.control(call_id, "hangup")
    except Exception:  # noqa: BLE001 - best effort: the worker also notices the caller leaving the room
        log.warning("could not signal worker for call %s", call_id)


# ------------------------------------------------------------------ end of a call
def finalize(s: Session, call: Call) -> None:
    """Runs once a phone call reaches a terminal state. Idempotent: usage is unique per call, and the campaign
    hook only touches an attempt that has no outcome yet."""
    if call.channel != "sip":
        return
    start = call.answered_at
    if start and call.ended_at and call.direction in ("inbound", "outbound"):
        seconds = max(0.0, (call.ended_at - start).total_seconds())
        trunk = s.get(SipTrunk, call.trunk_id) if call.trunk_id else None
        pulse = int((trunk.capabilities or {}).get("billing_pulse_seconds") or DEFAULT_PULSE_SECONDS) if trunk else 60
        pulse = min(max(pulse, 1), 60)
        billed = math.ceil(seconds / pulse) * pulse if seconds > 0 else 0
        other = call.to_number if call.direction == "outbound" else call.from_number
        country = None
        if other:
            try:
                country = phonenumbers.region_code_for_number(phonenumbers.parse(other))
            except phonenumbers.NumberParseException:
                country = None
        s.execute(
            insert(TelephonyUsage)
            .values(
                tenant_id=call.tenant_id,
                call_id=call.id,
                provider_key=trunk.provider_key if trunk else "simulated",
                trunk_id=call.trunk_id,
                direction=call.direction,
                country_code=country,
                connected_seconds=Decimal(str(round(seconds, 3))),
                pulse_seconds=pulse,
                billed_seconds=billed,
            )
            .on_conflict_do_nothing()
        )
    if call.campaign_id:
        from ..m07_campaigns.service import attempt_finished

        attempt_finished(s, call)


async def hangup(provider: str, room: str, participant: str | None) -> None:
    try:
        await adapter(provider).hangup(room=room, participant_identity=participant)
    except CarrierError as e:
        log.warning("hangup failed: %s", e)


# ------------------------------------------------------------------ trunks
async def sync_trunk(tenant_id: UUID, trunk_id: UUID) -> SipTrunk:
    """Creates the carrier-side trunk (LiveKit SIP) from the stored settings and the trunk's active numbers."""
    with session_scope(tenant_id=tenant_id) as s:
        t = s.get(SipTrunk, trunk_id)
        assert t is not None
        numbers = list(
            s.scalars(select(PhoneNumber.e164).where(PhoneNumber.trunk_id == t.id, PhoneNumber.status == "active"))
        )
        spec = TrunkSpec(
            id=str(t.id),
            name=t.name,
            direction=t.direction,
            address=t.address,
            transport=t.transport,
            auth_username=t.auth_username,
            auth_password=decrypt_secret(t.auth_secret_ciphertext) if t.auth_secret_ciphertext else None,
            allowed_addresses=list(t.allowed_addresses or []),
            numbers=numbers,
        )
        existing = {
            "inbound": t.livekit_inbound_trunk_id,
            "outbound": t.livekit_outbound_trunk_id,
            "dispatch": t.livekit_dispatch_rule_id,
        }
        provider, status = t.provider_key, t.status
    try:
        if status != "active":
            await adapter(provider).delete_trunk(existing)
            ids: dict[str, str | None] = {"inbound": None, "outbound": None, "dispatch": None}
        else:
            ids = await adapter(provider).sync_trunk(spec, existing)
        result, error = ("not_required" if provider == "simulated" else "synced"), None
    except CarrierError as e:
        ids, result, error = existing, "error", str(e)[:300]
    with session_scope(tenant_id=tenant_id) as s:
        t = s.get(SipTrunk, trunk_id)
        assert t is not None
        t.livekit_inbound_trunk_id = ids.get("inbound")
        t.livekit_outbound_trunk_id = ids.get("outbound")
        t.livekit_dispatch_rule_id = ids.get("dispatch")
        t.sync_status, t.sync_error = result, error
        t.updated_at = datetime.now(UTC)
        s.flush()
        s.expunge(t)
        return t
