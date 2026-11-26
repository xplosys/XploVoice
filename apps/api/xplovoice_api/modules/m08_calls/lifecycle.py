# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Call lifecycle: two linked state machines.

`state` is the 15-state call lifecycle from the addendum (section E, CR-003): what the call is doing on the
network. `status` is the voice session (the worker running the engine). Engine moves update the state through
STATUS_TO_STATE; carrier events update the state directly. Both are order-tolerant: a late or repeated update
never moves a call backwards, and a call in a terminal state never changes again. The only loops allowed are
in progress <-> on hold and in progress <-> transferring (a failed transfer comes back). Every accepted change
is written to call_state_transitions, and a rejected one is still kept by the caller as an event."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import object_session

from .models import Call

# ------------------------------------------------------------------ voice session status (Phase 3)
TERMINAL = frozenset({"completed", "failed", "abandoned"})
ORDER = {"created": 0, "queued": 1, "dispatching": 2, "connecting": 3, "active": 4, "ending": 5}
END_REASONS = frozenset(
    {
        "caller_hangup",
        "agent_ended",
        "user_ended",
        "max_duration",
        "silence_timeout",
        "no_provider",
        "worker_lost",
        "not_joined",
        "error",
        # Phase 6
        "transferred",
        "transfer_failed",
        "opted_out",
        "busy",
        "no_answer",
        "carrier_failed",
        "queue_timeout",
        "unavailable",
        "telephony_disabled",
        "no_route",
        "cancelled",
    }
)

# ------------------------------------------------------------------ the 15 call states (addendum E)
STATES = (
    "initiated",
    "queued",
    "routing",
    "ringing",
    "answered",
    "connected",
    "in_progress",
    "on_hold",
    "transferring",
    "completed",
    "failed",
    "busy",
    "no_answer",
    "cancelled",
    "disconnected",
)
TERMINAL_STATES = frozenset({"completed", "failed", "busy", "no_answer", "cancelled", "disconnected"})
RANK = {
    "initiated": 0,
    "queued": 1,
    "routing": 2,
    "ringing": 3,
    "answered": 4,
    "connected": 5,
    "in_progress": 6,
    "on_hold": 6,
    "transferring": 6,
}
LOOPS = frozenset({"in_progress", "on_hold", "transferring"})
# Which session status a terminal call state ends the voice session with.
STATE_TO_STATUS = {
    "completed": "completed",
    "disconnected": "completed",
    "failed": "failed",
    "busy": "abandoned",
    "no_answer": "abandoned",
    "cancelled": "abandoned",
}


def status_to_state(status: str, reason: str | None) -> str | None:
    if status == "abandoned":
        return "no_answer" if reason == "not_joined" else "cancelled"
    return {
        "queued": "queued",
        "dispatching": "queued",
        "connecting": "routing",
        "active": "in_progress",
        "completed": "completed",
        "failed": "failed",
    }.get(status)


def can_enter(current: str, new: str) -> bool:
    if current in TERMINAL_STATES or current == new or new not in STATES:
        return False
    if new in TERMINAL_STATES:
        return True
    if current in LOOPS and new in LOOPS:
        return True
    return RANK[new] > RANK.get(current, 99)


def enter(call: Call, new: str, *, source: str, reason: str | None = None, at: datetime | None = None) -> bool:
    """Moves the call to a new lifecycle state if that is a forward move. A terminal state also ends the voice
    session (status) with the same reason, so the worker's later updates are ignored."""
    from ..m04_telephony.models import CallStateTransition

    if not can_enter(call.state, new):
        return False
    now = at or datetime.now(UTC)
    before = call.state
    call.state = new
    call.state_changed_at = now
    if new in ("answered", "connected", "in_progress") and call.answered_at is None and call.channel == "sip":
        call.answered_at = now
    s = object_session(call)
    if s is not None:
        s.add(
            CallStateTransition(
                tenant_id=call.tenant_id, call_id=call.id, from_state=before, to_state=new, source=source, reason=reason
            )
        )
    if new in TERMINAL_STATES:
        _set_status(call, STATE_TO_STATUS[new], reason or new, now)
    return True


def _set_status(call: Call, new: str, reason: str | None, now: datetime) -> bool:
    if call.status in TERMINAL or call.status == new:
        return False
    if new not in TERMINAL and ORDER.get(new, -1) <= ORDER.get(call.status, 99):
        return False
    if new == "active" and call.connected_at is None:
        call.connected_at = now
    if new in TERMINAL:
        call.ended_at = now
        call.end_reason = reason if reason in END_REASONS else ("error" if new == "failed" else reason)
        start = call.answered_at or call.connected_at
        if start:
            call.duration_seconds = Decimal(str(round(max(0.0, (now - start).total_seconds()), 3)))
    call.status = new
    return True


def can_move(current: str, new: str) -> bool:
    if current in TERMINAL or current == new:
        return False
    if new in TERMINAL:
        return True
    return ORDER.get(new, -1) > ORDER.get(current, 99)


def move(call: Call, new: str, reason: str | None = None, *, source: str = "engine") -> bool:
    """Voice session update (worker, API). Also moves the lifecycle state forward where it maps to one."""
    if not can_move(call.status, new):
        return False
    now = datetime.now(UTC)
    _set_status(call, new, reason, now)
    target = status_to_state(new, reason)
    if target is not None:
        if new in TERMINAL and call.state == "transferring" and reason == "transferred":
            target = "completed"
        enter(call, target, source=source, reason=reason, at=now)
    return True
