# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Per-provider circuit breaker shared across API and worker processes through Redis (addendum L).

closed -> open after N availability failures within a window; open for a cool-down; then half-open, where a
single probe is let through (SET NX), and its result closes or re-opens the breaker. If Redis is unavailable
the breaker reports closed: availability of the provider is then decided by the call itself."""

import time

import redis

from ...core.config import get_settings
from ...core.ratelimit import client

WINDOW = 60


def _k(provider_key: str, part: str) -> str:
    return f"cb:{provider_key}:{part}"


def state(provider_key: str) -> str:
    try:
        until = client().get(_k(provider_key, "open_until"))
    except redis.RedisError:
        return "closed"
    if until is None:
        return "closed"
    return "open" if float(until) > time.time() else "half_open"


def allow(provider_key: str) -> bool:
    s = state(provider_key)
    if s == "closed":
        return True
    if s == "open":
        return False
    try:  # half-open: one probe at a time
        return bool(client().set(_k(provider_key, "probe"), "1", nx=True, ex=get_settings().breaker_open_seconds))
    except redis.RedisError:
        return True


def success(provider_key: str) -> None:
    try:
        client().delete(_k(provider_key, "fails"), _k(provider_key, "open_until"), _k(provider_key, "probe"))
    except redis.RedisError:
        pass


def failure(provider_key: str) -> None:
    s = get_settings()
    try:
        r = client()
        if state(provider_key) == "half_open":
            r.set(_k(provider_key, "open_until"), time.time() + s.breaker_open_seconds)
            r.delete(_k(provider_key, "probe"))
            return
        fails = r.incr(_k(provider_key, "fails"))
        r.expire(_k(provider_key, "fails"), WINDOW)
        if fails >= s.breaker_failure_threshold:
            r.set(_k(provider_key, "open_until"), time.time() + s.breaker_open_seconds)
            r.delete(_k(provider_key, "fails"))
    except redis.RedisError:
        pass


def snapshot(provider_key: str) -> dict:
    try:
        fails = int(client().get(_k(provider_key, "fails")) or 0)
    except redis.RedisError:
        return {"state": "unknown", "recent_failures": None}
    return {"state": state(provider_key), "recent_failures": fails}
