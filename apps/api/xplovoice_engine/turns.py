# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Voice activity detection and end-of-turn detection, measured in audio time (frame counts) so behaviour is the
same at any playback speed and fully deterministic in tests.

The default detector is energy-based with an adaptive noise floor. The design names Silero VAD; it plugs in
behind the same `Vad` interface once its runtime is packaged for the worker image (ADR-0006)."""

from collections import deque
from dataclasses import dataclass
from typing import Protocol

from .audio import FRAME_MS, rms


class Vad(Protocol):
    def is_speech(self, frame: bytes) -> bool: ...


class EnergyVad:
    def __init__(self, min_rms: float = 400.0, ratio: float = 3.0) -> None:
        self.floor = 100.0
        self.min_rms = min_rms
        self.ratio = ratio

    def is_speech(self, frame: bytes) -> bool:
        level = rms(frame)
        speech = level > max(self.min_rms, self.floor * self.ratio)
        if not speech:  # track background noise only while nobody speaks
            self.floor = 0.95 * self.floor + 0.05 * max(level, 1.0)
        return speech


@dataclass
class Utterance:
    pcm: bytes
    start_ms: int
    end_ms: int  # audio time of the last voiced frame


class TurnDetector:
    """Feeds frames; reports when speech starts, how long it has lasted, and a finished utterance once the
    caller has been silent for `endpoint_silence_ms`. Keeps 200 ms of pre-roll so first syllables survive."""

    PREROLL_MS = 200
    MIN_SPEECH_MS = 120

    def __init__(self, vad: Vad, endpoint_silence_ms: int) -> None:
        self.vad = vad
        self.endpoint_silence_ms = endpoint_silence_ms
        self.clock_ms = 0
        self.preroll: deque[bytes] = deque(maxlen=self.PREROLL_MS // FRAME_MS)
        self.buf: list[bytes] = []
        self.speaking = False
        self.start_ms = 0
        self.last_voice_ms = 0
        self.voiced_ms = 0

    @property
    def speech_ms(self) -> int:
        """Voiced audio in the current utterance (used for barge-in)."""
        return self.voiced_ms if self.speaking else 0

    def reset(self) -> None:
        self.buf, self.speaking, self.voiced_ms = [], False, 0
        self.preroll.clear()

    def feed(self, frame: bytes) -> tuple[bool, Utterance | None]:
        """Returns (speech_started_now, finished_utterance)."""
        self.clock_ms += FRAME_MS
        voiced = self.vad.is_speech(frame)
        started = False
        if not self.speaking:
            self.preroll.append(frame)
            if voiced:
                self.speaking, started = True, True
                self.start_ms = self.clock_ms - FRAME_MS * len(self.preroll)
                self.buf = list(self.preroll)
                self.preroll.clear()
                self.voiced_ms = FRAME_MS
                self.last_voice_ms = self.clock_ms
            return started, None
        self.buf.append(frame)
        if voiced:
            self.voiced_ms += FRAME_MS
            self.last_voice_ms = self.clock_ms
            return False, None
        if self.clock_ms - self.last_voice_ms < self.endpoint_silence_ms:
            return False, None
        utt = Utterance(b"".join(self.buf), self.start_ms, self.last_voice_ms)
        enough = self.voiced_ms >= self.MIN_SPEECH_MS
        self.reset()
        return False, utt if enough else None
