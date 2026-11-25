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
