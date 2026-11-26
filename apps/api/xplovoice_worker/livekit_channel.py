# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""LiveKit channel adapter. Browser WebRTC callers and SIP callers (Phase 6, through LiveKit SIP) both arrive
as room participants, so this one adapter serves both."""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator

from livekit import rtc

from xplovoice_engine.audio import FRAME_MS, FRAME_SAMPLES, RATE


class LiveKitChannel:
    speed = 1.0

    def __init__(self, room: rtc.Room) -> None:
        self.room = room
        self.source = rtc.AudioSource(RATE, 1, queue_size_ms=100)  # small queue: barge-in cuts audio quickly
        self.caller_track: asyncio.Future[rtc.Track] = asyncio.get_running_loop().create_future()
        self.left = asyncio.Event()
        self.dtmf: asyncio.Queue[str] = asyncio.Queue(maxsize=64)  # keypad tones from a phone caller
        room.on("track_subscribed", self._on_track)
        room.on("participant_disconnected", lambda p: self.left.set() if not p.identity.startswith("agent") else None)
        room.on("disconnected", lambda *_: self.left.set())
        room.on("sip_dtmf_received", self._on_dtmf)

    def _on_track(self, track: rtc.Track, _pub: rtc.RemoteTrackPublication, p: rtc.RemoteParticipant) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO and not self.caller_track.done():
            self.caller_track.set_result(track)

    def _on_dtmf(self, ev: rtc.SipDTMF) -> None:
        if ev.digit and ev.digit in "0123456789*#":
            with contextlib.suppress(asyncio.QueueFull):
                self.dtmf.put_nowait(ev.digit)

    @classmethod
    async def join(cls, url: str, token: str) -> "LiveKitChannel":
        room = rtc.Room()
        ch = cls(room)
        await room.connect(url, token, rtc.RoomOptions(auto_subscribe=True))
        track = rtc.LocalAudioTrack.create_audio_track("agent-voice", ch.source)
        await room.local_participant.publish_track(
            track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        )
        for p in room.remote_participants.values():  # caller joined before the worker
            for pub in p.track_publications.values():
                if pub.track and pub.kind == rtc.TrackKind.KIND_AUDIO and not ch.caller_track.done():
                    ch.caller_track.set_result(pub.track)
        return ch

    async def wait_for_caller(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(asyncio.shield(self.caller_track), timeout)
            return True
        except TimeoutError:
            return False

    async def frames(self) -> AsyncIterator[bytes]:
        track = await self.caller_track
        stream = rtc.AudioStream(track, sample_rate=RATE, num_channels=1, frame_size_ms=FRAME_MS)
        left = asyncio.create_task(self.left.wait())
        try:
            it = stream.__aiter__()
            while True:
                nxt = asyncio.create_task(it.__anext__())
                done, _ = await asyncio.wait({nxt, left}, return_when=asyncio.FIRST_COMPLETED)
                if left in done:
                    nxt.cancel()
                    return
                try:
                    ev = nxt.result()
                except StopAsyncIteration:
                    return
                yield bytes(ev.frame.data.cast("B"))
        finally:
            left.cancel()
            with contextlib.suppress(Exception):
                await stream.aclose()

    async def write_frame(self, frame: bytes) -> None:
        await self.source.capture_frame(rtc.AudioFrame(frame, RATE, 1, FRAME_SAMPLES))

    async def clear_output(self) -> None:
        self.source.clear_queue()

    async def send(self, event: dict) -> None:
        with contextlib.suppress(Exception):
            await self.room.local_participant.publish_data(json.dumps(event), reliable=True, topic="xv")

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self.room.disconnect()
