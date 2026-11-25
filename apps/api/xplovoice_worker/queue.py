# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Call dispatch consumer with leases.

Each call is one Redis stream entry that stays pending while a worker runs the call. The owning worker re-claims
its entries every `heartbeat` seconds, which resets their idle time. An entry idle for longer than `lease` means
its worker died: any worker takes it over with XAUTOCLAIM and resumes the call (Phase 3 kill-and-recover gate)."""

from dataclasses import dataclass

import redis.asyncio as aioredis

STREAM = "voice:jobs"
GROUP = "voice-workers"


@dataclass
class Job:
    entry_id: str
    call_id: str
    tenant_id: str
    token: str
    recovered: bool


def _s(v: bytes | str) -> str:
    return v.decode() if isinstance(v, bytes) else v


class CallQueue:
    def __init__(self, r: aioredis.Redis, consumer: str, *, lease_seconds: float = 15.0) -> None:
        self.r = r
        self.consumer = consumer
        self.lease_ms = int(lease_seconds * 1000)

    async def ensure_group(self) -> None:
        try:
            await self.r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    @staticmethod
    def _job(entry_id: bytes | str, fields: dict, recovered: bool) -> Job:
        f = {_s(k): _s(v) for k, v in fields.items()}
        return Job(_s(entry_id), f["call_id"], f["tenant_id"], f["token"], recovered)

    async def take_over(self, count: int = 1) -> list[Job]:
        """Calls whose worker stopped heartbeating."""
        res = await self.r.xautoclaim(STREAM, GROUP, self.consumer, min_idle_time=self.lease_ms, count=count)
        claimed = res[1] if len(res) > 1 else []
        return [self._job(eid, fields, True) for eid, fields in claimed if fields]

    async def next(self, block_ms: int = 2000) -> Job | None:
        res = await self.r.xreadgroup(GROUP, self.consumer, {STREAM: ">"}, count=1, block=block_ms)
        for _stream, entries in res or []:
            for eid, fields in entries:
                return self._job(eid, fields, False)
        return None

    async def heartbeat(self, entry_ids: list[str]) -> None:
        if entry_ids:
            await self.r.xclaim(STREAM, GROUP, self.consumer, min_idle_time=0, message_ids=entry_ids, justid=True)

    async def done(self, entry_id: str) -> None:
        await self.r.xack(STREAM, GROUP, entry_id)
        await self.r.xdel(STREAM, entry_id)
