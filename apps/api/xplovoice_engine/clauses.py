# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Splits a streamed LLM reply into speakable clauses, so text-to-speech starts on the first clause instead of
waiting for the whole reply (pipeline stage 10)."""

import re

_END = re.compile(r"[.!?।](?=\s)|[;:](?=\s)")
_SOFT = re.compile(r",(?=\s)")
SOFT_MIN = 40
HARD_MAX = 160


class ClauseSplitter:
    def __init__(self) -> None:
        self.buf = ""

    def feed(self, delta: str) -> list[str]:
        self.buf += delta
        out: list[str] = []
        while True:
            m = _END.search(self.buf)
            if not m and len(self.buf) >= SOFT_MIN:
                m = _SOFT.search(self.buf, SOFT_MIN // 2)
            if not m and len(self.buf) >= HARD_MAX:
                cut = self.buf.rfind(" ", 0, HARD_MAX)
                if cut > 0:
                    out.append(self.buf[:cut].strip())
                    self.buf = self.buf[cut:]
                    continue
            if not m:
                return [c for c in out if c]
            clause = self.buf[: m.end()].strip()
            self.buf = self.buf[m.end() :]
            if clause:
                out.append(clause)

    def flush(self) -> list[str]:
        rest, self.buf = self.buf.strip(), ""
        return [rest] if rest else []
