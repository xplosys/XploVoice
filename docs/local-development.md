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
