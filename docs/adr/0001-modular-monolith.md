# ADR-0001: Modular monolith control plane with separate voice workers

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys · Status: accepted

**Context.** HLD v1.0 §1 and §10 target Docker on Ubuntu without Kubernetes at launch, with real-time voice isolated
from the control plane.

**Decision.** One FastAPI application with one package per module (`modules/mNN_name`), each owning its models,
schemas and routes. Modules talk through service functions, not each other's tables. Voice workers (Phase 3) are a
separate deployable.

**Consequences.** One deploy and one database for the control plane; module boundaries are enforced by review and
package layout. A module can be extracted later because it owns its own routes and tables.
