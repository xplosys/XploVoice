# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Channel adapter contract: the only channel-aware part of the engine."""

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

from .audio import FRAME_BYTES, FRAME_MS


class Channel(Protocol):
    def frames(self) -> AsyncIterator[bytes]:
        """Caller audio, 20 ms 16 kHz mono frames, until the caller leaves."""
        ...

    async def write_frame(self, frame: bytes) -> None:
        """Queues one frame of agent audio; returns at the pace the caller hears it."""
        ...

    async def clear_output(self) -> None:
        """Drops agent audio that is queued but not yet heard (barge-in)."""
        ...

    async def send(self, event: dict) -> None:
        """Best-effort UI event to the caller's app (transcript, state). Never conversation-critical."""
        ...

    async def close(self) -> None: ...


class ScriptedChannel:
    """Test and benchmark channel. Caller audio is a script of PCM chunks fed at `speed` times real time;
    agent audio is consumed at the same pace. `heard` keeps everything the caller would have heard."""

    def __init__(self, script: list[bytes], speed: float = 1.0, tail_ms: int = 3000) -> None:
        self.script = script
        self.speed = speed
        self.tail_ms = tail_ms
        self.events: list[dict] = []
        self.heard = bytearray()
        self.closed = asyncio.Event()
        self.extend: asyncio.Queue[bytes] = asyncio.Queue()

    async def _tick(self) -> None:
        await asyncio.sleep(FRAME_MS / 1000 / self.speed)

    async def frames(self) -> AsyncIterator[bytes]:
        from .audio import frames as split
        from .audio import silence

        for chunk in self.script:
            for f in split(chunk):
                if self.closed.is_set():
                    return
                await self._tick()
                yield f
        tail = split(silence(self.tail_ms))
        while not self.closed.is_set():
            if not self.extend.empty():
                for f in split(self.extend.get_nowait()):
                    await self._tick()
                    yield f
                continue
            if not tail:
                return
            await self._tick()
            yield tail.pop(0)

    async def write_frame(self, frame: bytes) -> None:
        assert len(frame) == FRAME_BYTES
        await self._tick()
        self.heard.extend(frame)

    async def clear_output(self) -> None:
        return None

    async def send(self, event: dict) -> None:
        self.events.append(event)

    async def close(self) -> None:
        self.closed.set()
