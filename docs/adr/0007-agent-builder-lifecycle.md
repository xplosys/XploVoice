# ADR-0007: Agent builder, immutable versions and the publishing lifecycle

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys · Status: accepted for development

**Context.** The master prompt (§9) lists 25 builder fields and five lifecycle states (draft, testing, published,
paused, archived) and requires every call to record the exact agent version and provider/model versions. The
addendum (ADD-F) requires immutable agent versions. HLD v1.0 recommends seven states and defines rollback as
"activating a previous version; existing calls retain the exact version they started with". No document defines
agent tables, endpoints or template contents (CR-006, CR-019).

**Decision.**

**Versions**
- Every save writes a new immutable `agent_versions` row, unless nothing changed: the content hash (SHA-256 of the
  canonical JSON, including the agent's name, which the agent introduces itself by) matches the latest version.
- The runtime role can insert and read versions, never update them. Phase 3 versions (flat settings) are read
  through an upgrade in the schema; the stored rows are not rewritten.
- Two pointers on the agent: `current_version_id` (latest saved; what test calls use by default) and
  `published_version_id` (what live traffic reaches). Saving never changes what live callers reach.

**Lifecycle (MP §9 states)**
- draft → testing on the first test call; published by publishing; paused and resumed by owners and admins;
  archived from any state, restored to paused (if it was ever published) so it never returns straight to live traffic.
- HLD v1.0's extra states become conditions instead of states: "configured" = the readiness checks pass,
  "active" = published and not paused.
- Publishing a version requires its readiness checks to pass and a completed test call on exactly that version. An
  owner or admin may skip the test with a written reason, which is recorded in the publication history and the
  audit log. A version that was published before needs no new test.
- Rollback makes a previously published version live again. Running calls keep the version they started with.
- `agent_publications` is an append-only history of publish, rollback, pause, resume, archive and restore.
- Publishing, rollback, pause and resume need `agents:publish` (owner, admin). Agent designers build and test.

**Builder fields.** All 25 §9 fields are stored on the version (name and description on the agent). A provider is
chosen by choosing one of the tenant's routed models; the gateway tries it first and still fails over to the
tenant's other routes. A model that is not routed is refused by the readiness checks and ignored at run time, so an
agent can never reach a model the tenant has not routed. The voice belongs to the TTS model.

**Runtime.** The server composes the system prompt (instructions, purpose, tone, personality, name, business
hours) and decides business hours, escalation and fallback, then hands the worker flat engine settings. Healthcare
administrative agents always get an administrative-only guardrail that is not a field and cannot be edited away
(MP §21). Each call records the provider, model and model version that served each kind (`calls.providers_used`).

**Features that need later phases.** Knowledge bases and tool permissions are stored with the version and run from
Phase 5. Transfer to a phone number and recording run with telephony and consent (Phase 6); on a browser call an
escalation says the hand-over message and ends with `transfer_requested` or `escalated`. The UI labels each one.

**Templates.** Ten platform templates (MP §10) are written by XploVoice, seeded by migration 0004 and readable by every
tenant. Creating an agent copies the template into version 1; every field stays editable.

**Consequences.** What callers reach changes only through an explicit, audited publish or rollback. Old versions stay
reproducible. Phase 6 inbound and outbound routing must use `production_version()`, which returns nothing for draft,
testing, paused and archived agents.
