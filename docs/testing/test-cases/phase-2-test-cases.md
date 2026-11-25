# XploVoice test cases: Phase 2: AI providers, gateway and metering

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Synthetic data only. No PHI. Each automated case names the pytest test that checks it (`apps/api/tests`); manual cases are run in the browser.

22 test cases.

| ID | Area | Test case | Preconditions | Steps | Expected result | Type / automated test |
|---|---|---|---|---|---|---|
| TC-P2-01 | Adapters | OpenAI chat stream parsed | Simulated OpenAI replies | Stream a chat | Text and reported token usage parsed | Auto: test_openai_stream_parses_text_and_reported_usage |
| TC-P2-02 | Adapters | Self-hosted OpenAI-compatible server sends no key | Simulated Ollama | Stream a chat | No auth header sent | Auto: test_self_hosted_openai_compatible_sends_no_auth_header |
| TC-P2-03 | Adapters | Anthropic usage across events | Simulated Anthropic | Stream a chat | Usage added up correctly | Auto: test_anthropic_stream_usage_split_across_events |
| TC-P2-04 | Adapters | OpenAI transcription metered by duration | Simulated reply | Transcribe | Reported duration metered | Auto: test_openai_transcription_meters_reported_duration |
| TC-P2-05 | Adapters | Deepgram transcript and duration | Simulated reply | Transcribe | Text and duration parsed | Auto: test_deepgram_parses_transcript_and_duration |
| TC-P2-06 | Adapters | ElevenLabs speech as WAV | Simulated reply | Synthesize | 16 kHz WAV returned; characters metered | Auto: test_elevenlabs_returns_wav_audio_and_characters |
| TC-P2-07 | Adapters | Sarvam speech and transcription | Simulated replies | Synthesize and transcribe | Audio decoded; WAV length metered | Auto: test_sarvam_tts_decodes_base64_and_stt_meters_wav_length |
| TC-P2-08 | Adapters | Vendor errors classified, body never exposed | Simulated 401/429/503/400 | Call the vendor | Correct class; no response body in errors (4 cases) | Auto: test_error_classification_never_includes_response_body |
| TC-P2-09 | Adapters | Vendor unreachable is an outage | No network to vendor | Call the vendor | Availability error, next provider tried | Auto: test_connection_failure_is_an_availability_error |
| TC-P2-10 | Catalog | Vendors without accounts shown as awaiting configuration | Fresh install | Open AI providers | Awaiting configuration; no invented models or prices | Auto: test_catalog_marks_unconfigured_providers_awaiting_configuration; Manual: AI providers page |
| TC-P2-11 | Routing | No model chosen gives a clear error | No routes | Run the playground chat | 503 listing attempts; no made-up answer | Auto: test_no_route_means_clear_503_not_a_fake_answer |
| TC-P2-12 | Metering | Chat, speech and transcription metered with cost | Mock routes | Run all three | Tokens, characters and seconds with provider cost | Auto: test_chat_tts_stt_metered_in_provider_units_with_cost; Manual: Usage page |
| TC-P2-13 | Metering | Same request counted once | Mock routes | Send with the same idempotency key twice | One usage record | Auto: test_usage_is_idempotent_per_key |
| TC-P2-14 | Failover | First provider down | Two providers | Fail the first repeatedly | Next one answers; first skipped once the circuit opens | Auto: test_failover_to_next_provider_and_breaker_opens |
| TC-P2-15 | Routing | Unsupported language or capability skipped with reason | Providers with limits | Check a route for another language | Skipped with readable reason | Auto: test_language_and_capability_filters_explain_skips |
| TC-P2-16 | Customer keys | Own API key encrypted, hint only, customer-paid | Owner signed in | Add a key, use it | Encrypted at rest; hint shown; cost borne by customer | Auto: test_customer_key_is_encrypted_never_returned_and_cost_borne_by_customer |
| TC-P2-17 | Isolation | Other organisation's keys and usage invisible | Two tenants | List keys and usage | Only own data | Auto: test_other_tenants_keys_and_usage_are_invisible |
| TC-P2-18 | Isolation | App cannot edit catalog or rewrite usage | Database up | Write catalog / update usage as app role | Refused | Auto: test_runtime_role_cannot_write_catalog_or_rewrite_usage |
| TC-P2-19 | Roles | Who can configure and test AI | All roles | Try configure and test | Only owner and admin configure; designer can test | Auto: test_roles_limit_who_configures_and_tests |
| TC-P2-20 | Admin | AI catalog needs admin, 2FA and reason; PHI needs BAA | Platform admin | Edit catalog; mark PHI without BAA | Allowed with reason; PHI refused without signed BAA | Auto: test_admin_catalog_management_requires_mfa_admin_and_baa_for_phi |
| TC-P2-21 | Safety | Mock provider refused in staging and production | Production-like setting | Route to mock | Refused | Auto: test_mock_provider_is_refused_in_production_like_environments |
| TC-P2-22 | Web | Playground: chat, speech, transcription | Mock routes set | Run each in AI playground | Reply, playable audio, transcript; quantities with correct plurals | Manual: AI playground page |
