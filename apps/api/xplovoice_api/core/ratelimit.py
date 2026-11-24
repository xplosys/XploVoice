# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Fixed-window rate limiter backed by Redis. Fails closed in production, open in development if Redis is down."""

import logging
import time

import redis

from .config import get_settings
from .errors import too_many

log = logging.getLogger(__name__)
_client: redis.Redis | None = None


def client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(get_settings().redis_url, socket_timeout=0.5)
    return _client


def hit(bucket: str, limit: int, window_seconds: int = 60) -> None:
    key = f"rl:{bucket}:{int(time.time() // window_seconds)}"
    try:
        pipe = client().pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds + 5)
        count = pipe.execute()[0]
    except redis.RedisError:
        if get_settings().is_production_like:
            raise too_many("Service temporarily unavailable") from None
        log.warning("rate limiter unavailable; allowing request in %s", get_settings().environment)
        return
    if count > limit:
        raise too_many()
