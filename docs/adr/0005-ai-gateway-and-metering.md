# ADR-0005: AI gateway, provider routing and usage metering

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys · Status: accepted

**Context.** Voice agents need LLM, STT and TTS from several vendors (cloud and self-hosted), chosen per organisation
and per language, with automatic fallback, and every unit consumed must be traceable for billing. No supplied document
fixes vendor models or prices.

**Decision.**
- One adapter per vendor behind a common interface (`m03_ai/adapters`). Adapters never log or return response bodies,
  and classify errors as availability (fail over), rate limit (retry, then fail over) or request errors (stop).
- Candidates come from the organisation's ordered routes, else the platform default order. Each candidate is filtered by
  language, streaming, tool use, PHI eligibility (signed BAA only), provider status and circuit state, and every skip
  carries a reason that the UI shows.
- A Redis circuit breaker per provider opens after `XV_BREAKER_FAILURE_THRESHOLD` availability failures for
  `XV_BREAKER_OPEN_SECONDS`, then allows one probe. LLM streams fail over only before the first token.
- Usage is written in the provider's own units to append-only `usage_events`, unique per idempotency key. A separate
  `provider_cost_ledger` prices it from the rate card in force; with no rate card the line is stored `priced = false`
  rather than estimated. Usage on a customer's own key is marked `borne_by = customer`.
- The catalog (providers, models, rate cards, default routes) is managed only by platform admins with MFA, each change
  with an audited reason. XploVoice seeds no commercial models or prices; a dev-only mock provider exists for local
  development and tests and is refused in staging and production.

**Consequences.** Adding a vendor is one adapter plus catalog rows. Billing (Phase 7) reads usage and cost ledgers
without re-deriving units. Real-time latency budgets for the call path are measured in Phase 3 (CR-004).
