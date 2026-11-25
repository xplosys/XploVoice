# ADR-0006: Voice engine, LiveKit transport and worker dispatch

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys · Status: accepted for development; hosting choice open

**Context.** The design requires one voice engine for every channel. Browser calls (Phase 3) and SIP calls
(Phase 6) should differ only in how audio enters. Calls must survive a worker crash, and every stage must be
timed against the 1.5 s p95 first-audible target. LiveKit is named in the documents. Whether LiveKit is
self-hosted or LiveKit Cloud is still Xplosys's decision (Phase 0 report, section N).

**Decision.**

**LiveKit**
- LiveKit is the media layer. Development uses a self-hosted `livekit/livekit-server` in Docker Compose, with one
  TCP port and one UDP port for media.
- Staging and production hosting stays open until Xplosys chooses. Configuration is the same either way:
  `XV_LIVEKIT_URL`, `XV_LIVEKIT_INTERNAL_URL` and a key pair, and the dev key pair is refused outside development.
- Rooms have opaque random names.
- A browser token joins one room, can publish only the microphone, and expires in 10 minutes.
- The worker token joins one room for the call's maximum length.

**Engine**
- The engine (`xplovoice_engine`) has no LiveKit or API imports. It sees 20 ms frames of 16 kHz PCM through a
  `Channel` and reaches the platform only through `Backend`, which is the worker-scoped internal API.
- Speech, model calls and metering therefore go through the same AI gateway as the playground, with the same
  failover, circuit breakers and usage records.
- Turn-taking is measured in audio time.
- Replies are split into clauses so text-to-speech starts on the first clause.
- Barge-in cancels speech and the LLM stream. Only words the caller actually heard enter history.
- A cancelled LLM stream with no usage from the provider is metered as a flagged estimate (`usage_events.estimated`).

**Dispatch and recovery**
- The API puts each call on a Redis stream that a consumer group reads.
- The owning worker re-claims its entry every 2 s as a heartbeat. An entry idle past the lease (10 s) is taken
  over with XAUTOCLAIM by another worker.
- The new worker resumes from the durable transcript and says it is back.

**Internal API**
- Workers call only `/internal/v1`.
- Each call requires the shared worker key plus a per-call token naming one tenant and one call. Everything runs
  under that tenant's RLS context.

**Deviations, recorded honestly**
- Voice activity detection is energy-based with an adaptive noise floor, not Silero. Silero plugs in behind the
  same `Vad` interface once its runtime is packaged for the worker image and measured.
- Streaming STT partials are not used yet. STT runs on each finished utterance, and a streaming STT adapter is
  planned with vendor accounts.
- Both are tracked under CR-004.

**Consequences.**
- One code path serves every channel.
- Losing a worker costs the caller about the lease time of silence, not the call.
- Recovery is covered by a test that SIGKILLs a real worker process.
- Latency per stage is stored with every call and exported as Prometheus histograms (`xv_voice_stage_seconds`).
