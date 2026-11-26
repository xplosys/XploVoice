# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Carrier adapter contract (addendum D). The business layer never contains carrier-specific logic: it calls these
methods, and each adapter declares what its carrier can do (capabilities), so nothing assumes that every carrier
supports the same countries, transfer method, keypad tones or billing pulse."""

from dataclasses import dataclass, field
from typing import Protocol


class CarrierError(Exception):
    """The carrier refused or failed. The message is safe to show: it never carries credentials or bodies."""


@dataclass(frozen=True)
class TrunkSpec:
    id: str
    name: str
    direction: str  # inbound | outbound | both
    address: str | None
    transport: str
    auth_username: str | None
    auth_password: str | None
    allowed_addresses: list[str]
    numbers: list[str]


@dataclass(frozen=True)
class PlaceRequest:
    call_id: str
    room: str
    participant_identity: str
    to_e164: str
    from_e164: str
    outbound_trunk_id: str | None
    ring_timeout_seconds: int


@dataclass
class PlaceResult:
    outcome: str  # answered | busy | no_answer | failed
    sip_status: int | None = None
    refs: list[tuple[str, str]] = field(default_factory=list)  # (kind, ref) to find the call from carrier events
    detail: str | None = None


def outcome_for_sip_status(code: int | None) -> str:
    """Maps a final SIP response to a call outcome (RFC 3261 codes)."""
    if code is None:
        return "failed"
    if 200 <= code < 300:
        return "answered"
    if code in (486, 600, 603):
        return "busy"
    if code in (408, 480, 487):
        return "no_answer"
    return "failed"


class CarrierAdapter(Protocol):
    key: str

    async def sync_trunk(self, trunk: TrunkSpec, existing: dict[str, str | None]) -> dict[str, str | None]:
        """Creates or replaces the carrier-side trunk. Returns the carrier's ids for it."""
        ...

    async def delete_trunk(self, ids: dict[str, str | None]) -> None: ...

    async def place_call(self, req: PlaceRequest) -> PlaceResult: ...

    async def transfer(self, *, room: str, participant_identity: str, to_e164: str) -> None:
        """Hands the caller to another number (SIP REFER). Raises CarrierError if the carrier refused."""
        ...

    async def hangup(self, *, room: str, participant_identity: str | None) -> None: ...
