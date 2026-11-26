# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Customer-owned SIP trunks through LiveKit SIP (addendum D: "LiveKit SIP integration").

Talks to the LiveKit server's Twirp API with a short-lived token holding only the grants each request needs.
Inbound: one inbound trunk per customer trunk (its numbers and allowed source addresses) and a dispatch rule
that puts every caller in a new room named "xvin_<random>"; the API routes the call when LiveKit reports the
SIP participant (webhook). Outbound: an outbound trunk; each call creates a SIP participant in the call's room
and waits for the answer. Transfer uses SIP REFER (TransferSIPParticipant)."""

import json
import time

import httpx
import jwt

from ....core.config import get_settings
from .base import CarrierError, PlaceRequest, PlaceResult, TrunkSpec, outcome_for_sip_status

INBOUND_ROOM_PREFIX = "xvin_"
_transport: httpx.AsyncBaseTransport | None = None  # tests swap this
TRANSPORTS = {"udp": "SIP_TRANSPORT_UDP", "tcp": "SIP_TRANSPORT_TCP", "tls": "SIP_TRANSPORT_TLS"}


def _http_url() -> str:
    url = get_settings().livekit_internal_url
    return url.replace("wss://", "https://", 1).replace("ws://", "http://", 1).rstrip("/")


def _token(*, sip: bool = False, room: str | None = None) -> str:
    s = get_settings()
    now = int(time.time())
    claims: dict = {"iss": s.livekit_api_key, "sub": "xplovoice-api", "nbf": now - 5, "exp": now + 60}
    if sip:
        claims["sip"] = {"admin": True, "call": True}
    if room:
        claims["video"] = {"room": room, "roomAdmin": True}
    return jwt.encode(claims, s.livekit_api_secret, algorithm="HS256")


async def _twirp(service: str, method: str, body: dict, *, timeout: float = 15.0, room: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {_token(sip=service == 'SIP', room=room)}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(transport=_transport, timeout=timeout) as c:
            r = await c.post(
                f"{_http_url()}/twirp/livekit.{service}/{method}", content=json.dumps(body), headers=headers
            )
    except httpx.HTTPError as e:
        raise CarrierError(f"LiveKit SIP is unreachable ({type(e).__name__}).") from None
    if r.status_code >= 400:
        try:
            err = r.json()
        except ValueError:
            err = {}
        meta = err.get("meta") or {}
        code = meta.get("sip_status_code") or meta.get("sipStatusCode")
        raise SipCallError(
            str(err.get("msg") or f"LiveKit returned HTTP {r.status_code}")[:200],
            int(code) if str(code).isdigit() else None,
        )
    return r.json() if r.content else {}


class SipCallError(CarrierError):
    def __init__(self, message: str, sip_status: int | None = None) -> None:
        super().__init__(message)
        self.sip_status = sip_status


class LiveKitSip:
    key = "sip"

    async def sync_trunk(self, trunk: TrunkSpec, existing: dict[str, str | None]) -> dict[str, str | None]:
        await self.delete_trunk(existing)  # replace: LiveKit trunks are cheap to recreate and this avoids drift
        ids: dict[str, str | None] = {"inbound": None, "outbound": None, "dispatch": None}
        meta = json.dumps({"xv_trunk": trunk.id})
        if trunk.direction in ("inbound", "both"):
            body: dict = {"name": trunk.name, "numbers": trunk.numbers, "metadata": meta}
            if trunk.allowed_addresses:
                body["allowed_addresses"] = trunk.allowed_addresses
            if trunk.auth_username and trunk.auth_password:
                body["auth_username"], body["auth_password"] = trunk.auth_username, trunk.auth_password
            ids["inbound"] = (await _twirp("SIP", "CreateSIPInboundTrunk", {"trunk": body})).get("sip_trunk_id")
            rule = {
                "rule": {"dispatch_rule_individual": {"room_prefix": INBOUND_ROOM_PREFIX}},
                "trunk_ids": [ids["inbound"]],
                "name": f"xv {trunk.id}",
                "metadata": meta,
            }
            ids["dispatch"] = (await _twirp("SIP", "CreateSIPDispatchRule", rule)).get("sip_dispatch_rule_id")
        if trunk.direction in ("outbound", "both"):
            if not trunk.address:
                raise CarrierError("An outbound trunk needs the carrier's SIP address.")
            body = {
                "name": trunk.name,
                "address": trunk.address,
                "numbers": trunk.numbers,
                "metadata": meta,
                "transport": TRANSPORTS.get(trunk.transport, "SIP_TRANSPORT_UDP"),
            }
            if trunk.auth_username and trunk.auth_password:
                body["auth_username"], body["auth_password"] = trunk.auth_username, trunk.auth_password
            ids["outbound"] = (await _twirp("SIP", "CreateSIPOutboundTrunk", {"trunk": body})).get("sip_trunk_id")
        return ids

    async def delete_trunk(self, ids: dict[str, str | None]) -> None:
        if ids.get("dispatch"):
            await _ignore_missing(_twirp("SIP", "DeleteSIPDispatchRule", {"sip_dispatch_rule_id": ids["dispatch"]}))
        for k in ("inbound", "outbound"):
            if ids.get(k):
                await _ignore_missing(_twirp("SIP", "DeleteSIPTrunk", {"sip_trunk_id": ids[k]}))

    async def place_call(self, req: PlaceRequest) -> PlaceResult:
        if not req.outbound_trunk_id:
            return PlaceResult(outcome="failed", detail="The trunk isn't connected to LiveKit yet.")
        body = {
            "sip_trunk_id": req.outbound_trunk_id,
            "sip_call_to": req.to_e164,
            "sip_number": req.from_e164,
            "room_name": req.room,
            "participant_identity": req.participant_identity,
            "participant_name": "Phone",
            "wait_until_answered": True,
            "ringing_timeout": f"{req.ring_timeout_seconds}s",
        }
        try:
            info = await _twirp("SIP", "CreateSIPParticipant", body, timeout=req.ring_timeout_seconds + 15.0)
        except SipCallError as e:
            return PlaceResult(outcome=outcome_for_sip_status(e.sip_status), sip_status=e.sip_status, detail=str(e))
        except CarrierError as e:
            return PlaceResult(outcome="failed", detail=str(e))
        refs = [("participant", req.participant_identity)]
        if info.get("sip_call_id"):
            refs.append(("sip_call_id", str(info["sip_call_id"])))
        return PlaceResult(outcome="answered", sip_status=200, refs=refs)

    async def transfer(self, *, room: str, participant_identity: str, to_e164: str) -> None:
        body = {
            "room_name": room,
            "participant_identity": participant_identity,
            "transfer_to": f"tel:{to_e164}",
            "play_dialtone": False,
        }
        await _twirp("SIP", "TransferSIPParticipant", body, timeout=40.0, room=room)

    async def hangup(self, *, room: str, participant_identity: str | None) -> None:
        if participant_identity:
            await _ignore_missing(
                _twirp("RoomService", "RemoveParticipant", {"room": room, "identity": participant_identity}, room=room)
            )


async def _ignore_missing(coro) -> None:  # type: ignore[no-untyped-def]
    try:
        await coro
    except SipCallError:
        pass  # already gone
