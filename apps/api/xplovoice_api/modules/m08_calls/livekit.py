# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""LiveKit access tokens (HS256 JWT with a video grant). Each token joins exactly one opaque room, expires
quickly, and grants only what that participant needs: a browser caller may publish its microphone only."""

import time

import jwt

from ...core.config import get_settings


def room_token(identity: str, room: str, *, ttl_seconds: int, name: str | None = None, agent: bool = False) -> str:
    s = get_settings()
    now = int(time.time())
    grant: dict = {"room": room, "roomJoin": True, "canSubscribe": True, "canPublish": True, "canPublishData": True}
    if not agent:
        grant["canPublishSources"] = ["microphone"]
    claims = {
        "iss": s.livekit_api_key,
        "sub": identity,
        "nbf": now - 5,
        "exp": now + ttl_seconds,
        "video": grant,
        "name": name or identity,
    }
    if agent:
        claims["kind"] = "agent"
    return jwt.encode(claims, s.livekit_api_secret, algorithm="HS256")
