# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Audio helpers. The engine works in 20 ms frames of 16 kHz, 16-bit mono PCM."""

import io
import wave

import numpy as np

RATE = 16000
FRAME_MS = 20
FRAME_SAMPLES = RATE * FRAME_MS // 1000
FRAME_BYTES = FRAME_SAMPLES * 2


def rms(frame: bytes) -> float:
    a = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(a * a))) if a.size else 0.0


def to_wav(pcm: bytes, rate: int = RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def resample(pcm: bytes, src_rate: int, dst_rate: int = RATE) -> bytes:
    if src_rate == dst_rate or not pcm:
        return pcm
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    n = int(round(a.size * dst_rate / src_rate))
    x = np.linspace(0, a.size - 1, num=n)
    return np.interp(x, np.arange(a.size), a).astype(np.int16).tobytes()


def from_wav(data: bytes) -> bytes:
    """Decodes a PCM WAV (any rate, mono or stereo, 16-bit) to 16 kHz mono PCM."""
    with wave.open(io.BytesIO(data)) as w:
        if w.getsampwidth() != 2:
            raise ValueError("only 16-bit PCM WAV is supported")
        rate, channels = w.getframerate(), w.getnchannels()
        raw = w.readframes(w.getnframes())
    if channels > 1:
        a = np.frombuffer(raw, dtype=np.int16).reshape(-1, channels).mean(axis=1).astype(np.int16)
        raw = a.tobytes()
    return resample(raw, rate)


def frames(pcm: bytes) -> list[bytes]:
    """Splits PCM into whole frames, padding the last with silence."""
    out = [pcm[i : i + FRAME_BYTES] for i in range(0, len(pcm), FRAME_BYTES)]
    if out and len(out[-1]) < FRAME_BYTES:
        out[-1] = out[-1] + b"\x00" * (FRAME_BYTES - len(out[-1]))
    return out


def ms(nbytes: int) -> int:
    return nbytes * 1000 // (RATE * 2)


def tone(ms_: int, freq: float = 220.0, amp: int = 6000) -> bytes:
    """Synthetic 'speech' for tests and the benchmark: a voiced tone of the given length."""
    n = RATE * ms_ // 1000
    t = np.arange(n) / RATE
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.int16).tobytes()


def silence(ms_: int) -> bytes:
    return b"\x00\x00" * (RATE * ms_ // 1000)
