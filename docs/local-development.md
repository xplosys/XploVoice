# Local development

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

## With Docker

```bash
docker compose -f infra/compose/docker-compose.dev.yml up --build
```

The web app is at http://localhost:3000 and the API docs at http://localhost:8000/docs. All credentials in the compose
file and `.env.example` files are for local development only.

## Without Docker

Requires PostgreSQL 16, Redis 7, Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 22 and pnpm 10.

```bash
psql -U postgres -f infra/compose/postgres-init.sql          # roles and database
cd apps/api && uv sync && uv run alembic upgrade head
uv run uvicorn xplovoice_api.main:app --reload               # API on :8000
uv run pytest                                                 # tests run as the RLS-bound runtime role
cd ../web && pnpm install && pnpm dev                         # web on :3000
```

## Awaiting configuration

Outside production, creating an invitation returns its accept link in the API response and the Team page shows it,
because outbound email has no provider yet. In production the link is never returned.

## Platform admin

There is no self-service way to become a platform admin. Set `users.is_platform_admin = true` with the owner role, then
sign in with two-factor authentication turned on.

## Voice calls (Phase 3)

Docker Compose also starts `livekit`, a local LiveKit server on ports 7880, 7881 and 7882/udp, and `voice-worker`.

To place a browser test call:
1. Set the LLM, STT and TTS to the Mock models on **AI providers**.
2. Create an agent under **Voice agents**.
3. Press **Test call** and allow the microphone.

The mock voice answers with soft tones instead of words.

Without Docker, run the worker next to the API with `uv run python -m xplovoice_worker`. It needs a LiveKit server
at `XV_LIVEKIT_URL`.

Tests and the benchmark use a scripted caller made of synthetic audio instead of LiveKit. It is development and
test only:
`XV_WORKER_CHANNEL=scripted XV_WORKER_SCRIPT="silence:2000,tone:800,silence:3000" uv run python -m xplovoice_worker`.

## Knowledge, tools and integrations (Phase 5)

- **Knowledge base**: create one, add text or upload a file (PDF, Word, text, Markdown or CSV, up to 5 MB), then
  grant it to an agent under **Knowledge and tools**. Uploads are scanned first. Set `XV_CLAMAV_URL=tcp://host:3310`
  to use ClamAV; without it a built-in check is used, in development and test only.
- **Booking**: create a calendar under **Appointments** and choose it on the agent. Org-wide holidays close every
  calendar and the agents' business hours.
- **Text chat test**: on an agent's **Test call** page, type as a caller. The agent uses the same knowledge and
  tools as on a call. Chats are recorded under Calls but don't count as the test call needed to publish.
- **Approvals**: cancelling needs a person's approval by default. Approve or deny under **Business tools**.
- **Webhooks**: add one under **Integrations**. The address must be public https. The dispatcher runs inside the
  API (`XV_WEBHOOK_DISPATCHER=true`, default). SMS, email and CRM connectors are awaiting configuration.

## Telephony (Phase 6)

- Without a carrier, use the **simulated carrier** (development only). On Phone numbers: add a trunk of type
  "Simulated carrier", add a number (for example `080 4123 4567`), route it to a published agent, then use
  "Simulate an inbound call". Open the call to send carrier events (in progress, completed). Campaign calls to a
  number ending in 2 are busy, 3 not answered, 4 failed; anything else is answered.
- The dialer and the inbound queue run inside the API process (`XV_CAMPAIGN_DIALER=true`, the default; tests turn
  it off). Calling windows use the person's local time: in India, campaign calls wait until 09:00.
- Your own SIP trunk: needs a LiveKit server with SIP (`livekit/sip`) reachable at `XV_LIVEKIT_INTERNAL_URL`, and
  LiveKit webhooks sent to `POST /v1/webhooks/livekit` (signed with the LiveKit API key and secret). Add the trunk
  with your carrier's SIP address, username, password and allowed IPs, then point your carrier's numbers at the
  LiveKit SIP address.
- Kill switches: the organisation's "Pause all phone calls" on Phone numbers, and `XV_TELEPHONY_ENABLED=false` for
  the whole platform.

## Billing and analytics (Phase 7)

- No plans or prices are built in. As a platform admin, open **Admin → Billing**, add a tax rate and FX rate if you
  want them, create a plan with a fee and per-use prices, then activate it (and mark it default for new
  organisations if you like). Assign it to an organisation from the Organisations table.
- The billing job rates new use, closes ended periods and issues invoices inside the API every 5 minutes
  (`XV_BILLING_JOB=true`, default; tests turn it off). "Run billing now" and "Close the period now" do it at once.
- Pay invoices with the **test payment provider** (development only, refused in staging and production): pick
  "Payment succeeds" or "Payment declines" on the invoice. It signs its own webhook (`XV_TEST_PAYMENT_SECRET`) and
  settles through `POST /v1/webhooks/payments/test`. No money moves. The real gateway is awaiting configuration.
- `XV_BILLING_REQUIRE_PLAN=true` blocks calls for organisations without a plan (default off);
  `XV_BILLING_BLOCK_PAST_DUE` (default on) blocks new calls while an invoice is overdue
  (`XV_BILLING_INVOICE_DUE_DAYS`, default 15).
- **Analytics** shows calls by day in the organisation's time zone; charges appear only for owners and admins.

## Healthcare Mode (Phase 8)

Use synthetic data only. Never enter real patient information.

- Start the API with `XV_HEALTHCARE_ENABLED=true` (default off). The organisation must be in the US and its owner
  signed in with two-factor.
- As the owner, open **Healthcare** and ask for Healthcare Mode. Write a policy and have another member (for example
  an invited **privacy officer**) approve it. Set call retention on the **Retention** tab.
- As a platform admin with two-factor, open **Admin → Healthcare**: record a BAA for each AI provider you will use
  (for development the mock provider), mark it PHI-eligible, record the customer's BAA, run the control tests, then
  activate. The person who asked cannot be the one who activates; the gate lists anything missing.
- Once active, viewers and agent designers see calls without transcripts or numbers; every look at a call is in
  **Healthcare → PHI access log**. Anyone can **Report an incident**.
- `XV_HEALTHCARE_CONTROL_TEST_MAX_AGE_DAYS` (default 30) sets how recent the control tests must be.
