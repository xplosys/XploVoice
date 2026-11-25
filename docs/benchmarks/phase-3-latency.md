# Phase 3 latency benchmark (first run)

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

**What this measures.** This run measures XploVoice's own pipeline: end-of-turn detection, the internal API,
the AI gateway, clause splitting, metering and recording.

- Synthetic callers (scripted audio, 3 turns each) talk to one voice-worker process at real-time speed.
- The worker goes through the real API and Redis dispatch.
- STT, LLM and TTS use the **mock provider**, which answers almost instantly.

**What this does not measure.** Real vendor latency (Sarvam, OpenAI, Deepgram and the others) and WebRTC/SIP
transport are not measured: vendor accounts are awaiting configuration. Those stages will dominate real calls,
so these numbers are a floor, not evidence that the 1.5 s p95 target is met (CR-004 stays open).

**Setup.**
- Development container: 4 vCPU, 15 GB RAM.
- One uvicorn API process and one worker process.
- Agent end-of-turn silence: 500 ms.
- Script: `apps/api/scripts/voice_benchmark.py --levels 1,10,20`, run on 2026-11-25.

| Concurrent calls per worker | Completed | Turns measured | Stage | p50 ms | p95 ms | max ms |
|---|---|---|---|---|---|---|
| 1 | 1/1 | 3 | End-of-turn wait (configured 500 ms silence) | 500 | 500 | 500 |
| 1 | 1/1 | 3 | STT request (mock) | 11 | 17 | 17 |
| 1 | 1/1 | 3 | LLM first token (mock) | 7 | 8 | 8 |
| 1 | 1/1 | 3 | TTS first clause (mock) | 13 | 14 | 14 |
| 1 | 1/1 | 3 | Pipeline after end-of-turn | 54 | 59 | 59 |
| 1 | 1/1 | 3 | First audible response (from end of caller speech) | 554 | 559 | 559 |
| 10 | 10/10 | 30 | End-of-turn wait (configured 500 ms silence) | 500 | 500 | 500 |
| 10 | 10/10 | 30 | STT request (mock) | 20 | 61 | 71 |
| 10 | 10/10 | 30 | LLM first token (mock) | 12 | 68 | 68 |
| 10 | 10/10 | 30 | TTS first clause (mock) | 22 | 74 | 84 |
| 10 | 10/10 | 30 | Pipeline after end-of-turn | 78 | 230 | 232 |
| 10 | 10/10 | 30 | First audible response (from end of caller speech) | 578 | 730 | 732 |
| 20 | 20/20 | 60 | End-of-turn wait (configured 500 ms silence) | 500 | 500 | 500 |
| 20 | 20/20 | 60 | STT request (mock) | 16 | 76 | 92 |
| 20 | 20/20 | 60 | LLM first token (mock) | 13 | 48 | 68 |
| 20 | 20/20 | 60 | TTS first clause (mock) | 21 | 88 | 104 |
| 20 | 20/20 | 60 | Pipeline after end-of-turn | 70 | 236 | 263 |
| 20 | 20/20 | 60 | First audible response (from end of caller speech) | 570 | 736 | 763 |

**Reading it.**
- With instant providers, XploVoice adds about 55–80 ms at the median and up to about 260 ms at p95 under 20
  concurrent calls. The design budget allows 200 ms of headroom plus 150 ms for transport.
- The p95 growth under load comes from the single API process: each stage is an HTTP call that does database
  work, and those calls queue behind each other.
- Before pilots:
  - run more API workers, with workers placed next to the API;
  - repeat this benchmark with real vendors;
  - repeat it with real WebRTC and SIP audio on the target hardware.
