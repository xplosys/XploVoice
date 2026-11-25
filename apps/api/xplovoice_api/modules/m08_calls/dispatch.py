# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Hands calls to voice workers through a Redis stream consumed by a consumer group.

A worker keeps a call's stream entry pending for the whole call and re-claims it every few seconds as a
heartbeat. If the worker dies, the entry goes idle and another worker takes it over with XAUTOCLAIM and resumes
the call from its durable transcript (the kill-and-recover gate). The entry carries ids and a per-call worker
token only, never conversation content."""

import time
from uuid import UUID

import jwt

from ...core.config import get_settings
from ...core.ratelimit import client

STREAM = "voice:jobs"
GROUP = "voice-workers"


def worker_call_token(*, tenant_id: UUID, call_id: UUID, ttl_seconds: int) -> str:
    s = get_settings()
    now = int(time.time())
    claims = {
        "iss": s.jwt_issuer,
        "aud": "xv-worker",
        "typ": "worker",
        "tid": str(tenant_id),
        "cid": str(call_id),
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(claims, s.jwt_secret, algorithm="HS256")


def decode_worker_token(token: str) -> dict:
    s = get_settings()
    claims = jwt.decode(
        token,
        s.jwt_secret,
        algorithms=["HS256"],
        audience="xv-worker",
        issuer=s.jwt_issuer,
        options={"require": ["exp", "tid", "cid"]},
    )
    if claims.get("typ") != "worker":
        raise jwt.InvalidTokenError("wrong token type")
    return claims


def enqueue(*, tenant_id: UUID, call_id: UUID, max_seconds: int) -> str:
    token = worker_call_token(tenant_id=tenant_id, call_id=call_id, ttl_seconds=max_seconds + 600)
    entry = client().xadd(STREAM, {"call_id": str(call_id), "tenant_id": str(tenant_id), "token": token})
    return entry.decode() if isinstance(entry, bytes) else str(entry)


def control(call_id: UUID, command: str) -> None:
    """Out-of-band instruction to whichever worker holds the call (for example, hang up)."""
    client().publish(f"voice:control:{call_id}", command)
