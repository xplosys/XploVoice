# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Voice worker entry point."""

import asyncio
import contextlib
import logging
import os
import signal
import socket
import uuid
from collections.abc import Awaitable, Callable

import redis.asyncio as aioredis
from prometheus_client import Gauge, start_http_server

from xplovoice_engine.backend import CallEndedError, HttpBackend
from xplovoice_engine.session import CallSession

from .queue import CallQueue, Job

log = logging.getLogger("xplovoice.worker")
ACTIVE = Gauge("xv_worker_active_calls", "Calls running on this worker")

ChannelFactory = Callable[[str, str], Awaitable[object]]


async def livekit_channel(url: str, token: str) -> object:
    from .livekit_channel import LiveKitChannel

    return await LiveKitChannel.join(url, token)


def scripted_channel_factory(spec: str, speed: float) -> ChannelFactory:
    """Development and test only: a caller made of synthetic audio, e.g. "silence:1500,tone:800,silence:3000".
    Used by the kill-and-recover test and the latency benchmark; refused outside development and test."""
    from xplovoice_engine.audio import silence, tone
    from xplovoice_engine.channel import ScriptedChannel

    def build() -> list[bytes]:
        parts = []
        for item in spec.split(","):
            kind, ms = item.split(":")
            parts.append(tone(int(ms)) if kind == "tone" else silence(int(ms)))
        return parts

    async def factory(url: str, token: str) -> object:
        return ScriptedChannel(build(), speed=speed)

    return factory


class Worker:
    def __init__(
        self,
        *,
        redis_url: str,
        api_url: str,
        worker_key: str,
        max_calls: int = 4,
        lease_seconds: float = 10.0,
        heartbeat_seconds: float = 2.0,
        caller_wait_seconds: float = 60.0,
        channel_factory: ChannelFactory = livekit_channel,
        transport: object | None = None,
    ) -> None:
        self.id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.r = aioredis.Redis.from_url(redis_url)
        self.q = CallQueue(self.r, self.id, lease_seconds=lease_seconds)
        self.api_url, self.worker_key = api_url, worker_key
        self.max_calls, self.heartbeat_seconds = max_calls, heartbeat_seconds
        self.caller_wait = caller_wait_seconds
        self.channel_factory, self.transport = channel_factory, transport
        self.running: dict[str, asyncio.Task] = {}
        self.stopping = asyncio.Event()

    async def run(self) -> None:
        await self.q.ensure_group()
        beat = asyncio.create_task(self._heartbeat())
        log.info("worker %s ready", self.id)
        try:
            while not self.stopping.is_set():
                if len(self.running) >= self.max_calls:
                    await asyncio.sleep(0.2)
                    continue
                jobs = await self.q.take_over() or ([j] if (j := await self.q.next(block_ms=1000)) else [])
                for job in jobs:
                    self.running[job.entry_id] = asyncio.create_task(self._run_call(job))
        finally:
            beat.cancel()
            for t in self.running.values():  # graceful stop: finish calls in progress
                with contextlib.suppress(Exception):
                    await t
            await self.r.aclose()

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            with contextlib.suppress(Exception):
                await self.q.heartbeat(list(self.running))

    async def _run_call(self, job: Job) -> None:
        ACTIVE.inc()
        backend = HttpBackend(self.api_url, self.worker_key, job.call_id, job.token, transport=self.transport)  # type: ignore[arg-type]
        channel = None
        try:
            boot = await backend.bootstrap(self.id)
            channel = await self.channel_factory(boot.livekit_url, boot.livekit_token)
            wait = getattr(channel, "wait_for_caller", None)
            if wait and not await wait(self.caller_wait):
                await backend.set_state("abandoned", "not_joined")
                return
            reason = await CallSession(backend, channel, boot, worker_id=self.id).run()  # type: ignore[arg-type]
            log.info("call %s ended: %s%s", job.call_id, reason, " (recovered)" if job.recovered else "")
        except CallEndedError:
            log.info("call %s already ended", job.call_id)
        except Exception:
            log.exception("call %s failed", job.call_id)
            with contextlib.suppress(Exception):
                await backend.set_state("failed", "error")
        finally:
            if channel is not None:
                with contextlib.suppress(Exception):
                    await channel.close()  # type: ignore[attr-defined]
            await backend.aclose()
            with contextlib.suppress(Exception):
                await self.q.done(job.entry_id)
            self.running.pop(job.entry_id, None)
            ACTIVE.dec()


def main() -> None:
    logging.basicConfig(level=os.environ.get("XV_LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # request lines carry call ids, not useful at INFO
    port = int(os.environ.get("XV_WORKER_METRICS_PORT", "9100"))
    if port:
        start_http_server(port, addr=os.environ.get("XV_WORKER_METRICS_ADDR", "127.0.0.1"))
    env = os.environ.get("XV_ENVIRONMENT", "development")
    factory: ChannelFactory = livekit_channel
    if os.environ.get("XV_WORKER_CHANNEL") == "scripted":
        if env not in ("development", "test"):
            raise SystemExit("The scripted channel is for development and tests only")
        factory = scripted_channel_factory(
            os.environ.get("XV_WORKER_SCRIPT", "silence:2000,tone:800,silence:3000"),
            float(os.environ.get("XV_WORKER_SPEED", "1")),
        )
    w = Worker(
        redis_url=os.environ.get("XV_REDIS_URL", "redis://localhost:6379/0"),
        api_url=os.environ.get("XV_INTERNAL_API_URL", "http://localhost:8000"),
        worker_key=os.environ.get("XV_WORKER_KEY", "dev-only-worker-key"),
        max_calls=int(os.environ.get("XV_WORKER_MAX_CALLS", "4")),
        lease_seconds=float(os.environ.get("XV_WORKER_LEASE_SECONDS", "10")),
        heartbeat_seconds=float(os.environ.get("XV_WORKER_HEARTBEAT_SECONDS", "2")),
        channel_factory=factory,
    )

    async def runner() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, w.stopping.set)
        await w.run()

    asyncio.run(runner())


if __name__ == "__main__":
    main()
