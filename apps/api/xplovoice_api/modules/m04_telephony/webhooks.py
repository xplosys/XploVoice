# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Carrier webhooks (addendum D, CR-003). Every request is verified before anything is read from it, then each
event is stored once per carrier event id, so a retried, delayed or out-of-order delivery is harmless.

- /v1/webhooks/livekit: LiveKit signs each webhook with a JWT (the API key as issuer, the API secret as key) that
  carries the SHA-256 of the body. A phone caller joining an inbound room (prefix xvin_) is routed; a phone
  participant leaving, or the room closing, ends the call.
- /v1/webhooks/telephony/simulated: the development carrier's status events (HMAC with a timestamp window)."""

import base64
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Header, Request
from starlette.concurrency import run_in_threadpool

from ...core.config import get_settings
from ...core.errors import bad_request, not_found, unauthorized
from ..m06_inbound.service import route_inbound
from . import service as tel
from .adapters import simulated
from .adapters.livekit_sip import INBOUND_ROOM_PREFIX

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"], include_in_schema=False)
log = logging.getLogger("xplovoice.webhooks")
PHONE_ROOMS = (INBOUND_ROOM_PREFIX, "xvout_")
SIMULATED_STATES = frozenset(
    {
        "ringing",
        "answered",
        "connected",
        "in_progress",
        "completed",
        "busy",
        "no_answer",
        "failed",
        "cancelled",
        "disconnected",
    }
)
MAX_BODY = 64 * 1024


def verify_livekit(body: bytes, authorization: str | None) -> bool:
    s = get_settings()
    if not authorization:
        return False
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = jwt.decode(
            token, s.livekit_api_secret, algorithms=["HS256"], issuer=s.livekit_api_key, options={"verify_aud": False}
        )
    except jwt.PyJWTError:
        return False
    digest = base64.b64encode(hashlib.sha256(body).digest()).decode()
    return hmac.compare_digest(str(claims.get("sha256", "")), digest)


def _ts(value: object) -> datetime:
    try:
        return datetime.fromtimestamp(float(value), UTC)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return datetime.now(UTC)


async def _read(request: Request) -> bytes:
    body = await request.body()
    if len(body) > MAX_BODY:
        raise bad_request("too_large", "Webhook body is too large")
    return body


@router.post("/livekit")
async def livekit_webhook(request: Request, authorization: str | None = Header(default=None)) -> dict:
    body = await _read(request)
    if not verify_livekit(body, authorization):
        raise unauthorized("invalid_signature", "Webhook signature is invalid")
    try:
        ev = json.loads(body)
    except ValueError:
        raise bad_request("invalid_body", "Webhook body is not JSON") from None
    kind = str(ev.get("event", ""))
    room = str((ev.get("room") or {}).get("name", ""))
    if not room.startswith(PHONE_ROOMS):
        return {"result": "ignored"}  # browser test calls end through the worker, not through webhooks
    p = ev.get("participant") or {}
    is_phone = str(p.get("kind", "")).upper() in ("SIP", "3")
    attrs = p.get("attributes") or {}
    event_id = str(ev.get("id") or f"{kind}:{room}:{p.get('identity', '')}")
    at = _ts(ev.get("createdAt"))
    if kind == "participant_joined" and is_phone and room.startswith(INBOUND_ROOM_PREFIX):
        dialled = attrs.get("sip.trunkPhoneNumber") or ""
        routed = await route_inbound(
            room=room,
            dialled=dialled,
            caller=attrs.get("sip.phoneNumber"),
            provider="sip",
            participant_identity=p.get("identity"),
            sip_call_id=attrs.get("sip.callID"),
        )
        return {"result": routed.result}
    if kind == "participant_joined" and is_phone:
        state, reason = "in_progress", None
    elif kind == "participant_left" and is_phone:
        state, reason = "disconnected", "caller_hangup"
    elif kind == "room_finished":
        state, reason = "disconnected", "caller_hangup"
    else:
        return {"result": "ignored"}
    result, _, _ = await run_in_threadpool(
        tel.ingest,
        tel.CarrierEvent(
            provider="sip",
            event_id=event_id,
            type=kind,
            state=state,
            occurred_at=at,
            room=room,
            reason=reason,
            data={"identity": p.get("identity"), "sip_status": attrs.get("sip.callStatus")},
        ),
    )
    return {"result": result}


@router.post("/telephony/{provider}")
async def carrier_webhook(
    provider: str, request: Request, x_carrier_signature: str | None = Header(default=None)
) -> dict:
    if provider != "simulated":
        raise not_found()  # other carriers report through LiveKit, or are awaiting configuration
    if get_settings().is_production_like:
        raise not_found()
    body = await _read(request)
    if not simulated.verify(body, x_carrier_signature):
        raise unauthorized("invalid_signature", "Webhook signature is invalid")
    try:
        ev = json.loads(body)
        event_id, ref, status = str(ev["id"]), str(ev["call"]), str(ev["status"])
    except (ValueError, KeyError, TypeError):
        raise bad_request("invalid_body", "Webhook body is not a carrier event") from None
    if status not in SIMULATED_STATES:
        raise bad_request("invalid_status", "Unknown call status")
    reason = {"failed": "carrier_failed", "disconnected": "caller_hangup", "completed": "caller_hangup"}.get(status)
    result, _, call_id = await run_in_threadpool(
        tel.ingest,
        tel.CarrierEvent(
            provider="simulated",
            event_id=event_id,
            type="status",
            state=status,
            occurred_at=_ts(ev.get("at")),
            ref_kind="call",
            ref=ref,
            reason=reason,
            data={"sip_status": ev.get("sip_status")},
        ),
    )
    return {"result": result, "call_id": str(call_id) if call_id else None}
