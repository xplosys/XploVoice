# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""XploVoice common voice engine (M09 orchestration + M10 runtime core).

One engine for every channel: it sees 20 ms frames of 16 kHz mono PCM in, and writes the same out. The channel
adapter (LiveKit today, which carries both browser WebRTC and SIP) is the only part that knows where audio comes
from. The engine never imports the API package and talks to the platform only through `Backend`, so tests drive
it with synthetic audio and no LiveKit at all (Phase 0 report, section E)."""
