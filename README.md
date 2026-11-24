# XploVoice

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys

Multi-tenant AI voice agent SaaS for the India and US markets.

| Path | What |
|---|---|
| `apps/api` | FastAPI control plane (modular monolith, PostgreSQL with forced row-level security) |
| `apps/web` | Next.js app: public site, tenant dashboard, platform admin |
| `infra/compose` | Local development stack |
| `docs` | Module register, change requests, ADRs, acceptance reports |

Start with [docs/local-development.md](docs/local-development.md). Design baseline: HLD v1.0, HLD v1.3 and LLD v1.3
(held outside the repository).
