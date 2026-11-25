# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Call lifecycle (Phase 3 subset of the 15-state model in CR-003; telephony states arrive with M04 in Phase 6).

Transitions are order-tolerant: a late or repeated update never moves a call backwards, and a terminal call
never changes again. The rejected update is still kept as a call event, so nothing is silently lost."""

from datetime import UTC, datetime
from decimal import Decimal

from .models import Call

TERMINAL = frozenset({"completed", "failed", "abandoned"})
ORDER = {"created": 0, "dispatching": 1, "connecting": 2, "active": 3, "ending": 4}
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
    }
)


def can_move(current: str, new: str) -> bool:
    if current in TERMINAL or current == new:
        return False
    if new in TERMINAL:
        return True
    return ORDER.get(new, -1) > ORDER.get(current, 99)


def move(call: Call, new: str, reason: str | None = None) -> bool:
    if not can_move(call.status, new):
        return False
    now = datetime.now(UTC)
    if new == "active" and call.connected_at is None:
        call.connected_at = now
    if new in TERMINAL:
        call.ended_at = now
        call.end_reason = reason if reason in END_REASONS else ("error" if new == "failed" else reason)
        if call.connected_at:
            call.duration_seconds = Decimal(str(round((now - call.connected_at).total_seconds(), 3)))
    call.status = new
    return True
