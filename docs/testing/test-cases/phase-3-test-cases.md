# XploVoice test cases: Phase 3: common voice engine

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Synthetic data only. No PHI. Each automated case names the pytest test that checks it (`apps/api/tests`); manual cases are run in the browser.

28 test cases.

| ID | Area | Test case | Preconditions | Steps | Expected result | Type / automated test |
|---|---|---|---|---|---|---|
| TC-P3-01 | Engine | End-of-turn after the pause; clicks ignored | None | Feed 60 ms click, then 800 ms speech + 600 ms silence | No turn for the click; one turn for the speech | Auto: test_engine::test_turn_detector_endpoints_after_silence_and_ignores_clicks |
| TC-P3-02 | Engine | Speech starts on the first clause | None | Stream a reply in pieces | First sentence released before the reply ends | Auto: test_clause_splitter_starts_speech_on_first_clause |
| TC-P3-03 | Engine | Full conversation turn | Fake platform | Greeting, caller speaks, silence | Greeting, caller line, reply recorded in order with timings and providers | Auto: test_full_conversation_turn |
| TC-P3-04 | Barge-in | Caller interrupts the agent | Long reply | Caller speaks 1 s during the reply | Agent stops; only heard words kept; next reply sees them | Auto: test_barge_in_cuts_reply_and_keeps_only_spoken_words; Manual: talk over the agent in a test call |
| TC-P3-05 | Barge-in | Short 'uh-huh' does not interrupt | Long reply | Caller makes a 100 ms sound | Agent keeps talking | Auto: test_short_backchannel_does_not_interrupt |
| TC-P3-06 | Barge-in | Agent set to not interruptible | Interruptible off | Caller speaks during reply | Agent finishes the reply | Auto: test_not_interruptible_agent_finishes_its_reply |
| TC-P3-07 | Failover | No STT or LLM provider | Provider unavailable | Caller speaks | Fixed apology spoken; call ends as failed: no provider (2 cases) | Auto: test_no_provider_plays_fixed_message_and_ends |
| TC-P3-08 | Failover | No TTS provider | TTS unavailable | Start call | Call ends cleanly without audio | Auto: test_no_tts_ends_cleanly_without_audio |
| TC-P3-09 | Guards | Silence: check-in then end | Silence limit 5 s | Caller stays silent | 'Are you still there?', then goodbye and end | Auto: test_silence_prompts_then_ends |
| TC-P3-10 | Guards | Maximum call length | Limit 30 s | Keep call open | Time-limit message, call ends | Auto: test_max_duration_guard |
| TC-P3-11 | Recovery | Resumed call keeps history | Recovered call | Worker resumes | Says it is back; earlier turns kept | Auto: test_resumed_call_keeps_history_and_apologises |
| TC-P3-12 | Audio | Provider audio converted to 16 kHz | 24 kHz WAV | Decode | Correct length at 16 kHz | Auto: test_audio_roundtrip_resamples_to_16k |
| TC-P3-13 | Agents | Versions immutable; calls pin version | Owner | Create agent, save again | Version 2 created; versions cannot be edited | Auto: test_voice::test_agent_versions_are_immutable_and_calls_pin_them; Manual: Voice agents page |
| TC-P3-14 | Voice session | Browser token scoped and short-lived | Agent exists | Start a test call | Token for one room, microphone only, 10 min; opaque room name; call dispatched | Auto: test_voice_session_token_is_scoped_short_lived_and_dispatched |
| TC-P3-15 | Admission | Live-call limit per organisation | Limit 2 | Start a third call | 429 too_many_calls | Auto: test_concurrent_call_limit |
| TC-P3-16 | Roles | Who can call and manage agents | Viewer and designer | Viewer starts call / creates agent; designer starts call | Viewer 403; designer allowed; viewer can list calls | Auto: test_roles_for_calls |
| TC-P3-17 | Worker API | Worker key and call-bound token required | Two calls | Call internal API without key, with user token, with call 1 token on call 2 | 401, 401, 404; correct pair works | Auto: test_internal_api_requires_worker_key_and_matching_call_token |
| TC-P3-18 | End to end | Call through real API, gateway and metering | Mock routes, agent | Run a scripted call | Completed; transcript; timings; usage metered against the call | Auto: test_browser_call_end_to_end_through_api_and_gateway |
| TC-P3-19 | Failover | Call with no providers configured | No routes | Run a scripted call | Ends as failed: no provider; no audio | Auto: test_call_with_no_provider_ends_cleanly_as_failed |
| TC-P3-20 | Lifecycle | Late updates never move a call backwards | Completed call | Send 'active' after 'completed'; recover it | Stays completed; ignored update recorded; recovery refused | Auto: test_late_or_repeated_state_updates_never_move_a_call_backwards |
| TC-P3-21 | Lifecycle | Recording is idempotent | Call exists | Send the same events and lines 3 times | Stored once | Auto: test_recording_is_idempotent |
| TC-P3-22 | Isolation | Calls and agents isolated between organisations | Two tenants | B reads, ends, or calls A's call/agent | 404 everywhere; B's list empty | Auto: test_calls_are_isolated_between_tenants |
| TC-P3-23 | Calls | End a call from the dashboard | Call started | Press End call | Call ends; ending twice gives 409 | Auto: test_end_call_from_dashboard |
| TC-P3-24 | Worker API | Unknown call refused | None | Worker token for a non-existent call | 404 | Auto: test_unknown_call_returns_404_for_worker |
| TC-P3-25 | Recovery | Worker killed mid-call is recovered | API and two worker processes | SIGKILL the first worker after the first caller turn | Second worker takes over; call completes; recoveries = 1 | Auto: test_worker_recovery::test_worker_killed_mid_call_is_recovered_by_another_worker |
| TC-P3-26 | Benchmark | First latency benchmark | Development stack | Run scripts/voice_benchmark.py at 1, 10, 20 calls | All calls complete; per-stage p50/p95 reported | Auto: scripts/voice_benchmark.py |
| TC-P3-27 | Web | Browser test call with microphone | Docker stack incl. LiveKit; mock routes; agent | Voice agents > Test call > Start call; speak; then interrupt | Agent greets (soft tones), live transcript shows both sides, interrupting stops the agent, End call works | Manual: Test call page |
| TC-P3-28 | Web | Calls list and call detail | A finished call | Open Calls, then the call | Status, length, transcript, per-turn timings, providers used | Manual: Calls pages |
