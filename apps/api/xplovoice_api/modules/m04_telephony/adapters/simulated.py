# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Simulated carrier: development and tests only, refused in staging and production like the mock AI provider.

It dials nobody. The outcome of a call depends on the last digit of the number called, so tests and demos can
show every path: 2 busy, 3 no answer, 4 carrier failure, anything else answered. A transfer to a number ending
in 9 fails. Carrier status events come back through the same verified webhook path as a real carrier's."""

import hashlib
import hmac
import json
import time
import uuid

from ....core.config import get_settings
from .base import CarrierError, PlaceRequest, PlaceResult, TrunkSpec

OUTCOMES = {"2": ("busy", 486), "3": ("no_answer", 480), "4": ("failed", 503)}


def _allowed() -> None:
    if get_settings().is_production_like:
        raise CarrierError("The simulated carrier is for development and tests only.")


def sign(body: bytes, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    mac = hmac.new(get_settings().simulated_carrier_secret.encode(), f"{ts}.".encode() + body, hashlib.sha256)
    return f"t={ts},v1={mac.hexdigest()}"


def verify(body: bytes, header: str | None) -> bool:
    """Signature and timestamp window: a replayed or altered request fails."""
    if not header:
        return False
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs(time.time() - ts) > get_settings().carrier_webhook_tolerance_seconds:
        return False
    expected = sign(body, ts).split("v1=", 1)[1]
    return hmac.compare_digest(expected, parts.get("v1", ""))


def event(call_ref: str, status: str, *, sip_status: int | None = None) -> bytes:
    return json.dumps(
        {
            "id": f"sim_{uuid.uuid4().hex}",
            "call": call_ref,
            "status": status,
            "sip_status": sip_status,
            "at": time.time(),
        }
    ).encode()


class SimulatedCarrier:
    key = "simulated"

    async def sync_trunk(self, trunk: TrunkSpec, existing: dict[str, str | None]) -> dict[str, str | None]:
        _allowed()
        return {}

    async def delete_trunk(self, ids: dict[str, str | None]) -> None:
        return None

    async def place_call(self, req: PlaceRequest) -> PlaceResult:
        _allowed()
        outcome, code = OUTCOMES.get(req.to_e164[-1], ("answered", 200))
        ref = f"simcall_{req.call_id}"
        return PlaceResult(outcome=outcome, sip_status=code, refs=[("call", ref)])

    async def transfer(self, *, room: str, participant_identity: str, to_e164: str) -> None:
        _allowed()
        if to_e164.endswith("9"):
            raise CarrierError("The other number didn't answer the transfer.")

    async def hangup(self, *, room: str, participant_identity: str | None) -> None:
        return None
