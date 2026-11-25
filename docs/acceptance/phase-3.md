# Phase 3 acceptance report: common voice engine

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Scope: M08 calls, M09 engine, M10 workers, minimal versioned agents (M05 slice), and web pages for agents, browser
test calls, the calls list and call detail.

Data used is synthetic only, with no PHI. This report does not claim production readiness.

## Exit gate (Phase 0 roadmap)

| Gate | Evidence |
|---|---|
| Browser call end to end | `test_browser_call_end_to_end_through_api_and_gateway` runs the engine against the real API, gateway, metering and recording. A live WebRTC call through LiveKit is run with Docker on the development PC (see the test report). |
| Barge-in test | `test_barge_in_cuts_reply_and_keeps_only_spoken_words`, `test_short_backchannel_does_not_interrupt`, `test_not_interruptible_agent_finishes_its_reply` |
| Worker kill-and-recover test | `test_worker_killed_mid_call_is_recovered_by_another_worker`: SIGKILL of a real worker process mid-call; a second worker takes over and completes the call |
| First latency benchmark published | [phase-3-latency.md](../benchmarks/phase-3-latency.md) (mock providers; real vendors pending) |

## Definition of done (master prompt §31)

| Criterion | Evidence |
|---|---|
| Migrations | `0003_voice_engine` upgrades, downgrades to 0002 and upgrades again |
| Automated tests | 83 pass, 26 of them new: 13 engine, 12 voice API and 1 real-process recovery test. Ruff, web typecheck, lint and build are clean |
| Authorization | `calls:test` for owner, admin and agent designer; `agents:manage` for owner, admin and agent designer; viewers can read only |
| Tenant isolation | FORCE RLS on agents, versions, calls, events and transcripts; IDOR tests; worker tokens bound to one call |
| Audit | Agent created, updated and archived; call started; end requested |
| Documentation | ADR-0006, module register, CR log (CR-002, 003, 004, 010, 012, 013), benchmark |

## Not done in Phase 3 (by design or awaiting configuration)

- Silero VAD and streaming STT partials: energy VAD and per-utterance STT for now (ADR-0006, CR-004).
- Real-vendor latency: vendor accounts are awaiting configuration.
- LiveKit hosting for staging and production: self-hosted or LiveKit Cloud is Xplosys's choice.
- Tools, RAG and human transfer: Phases 5 and 6. With no provider available, the call ends with a message instead of a transfer.
