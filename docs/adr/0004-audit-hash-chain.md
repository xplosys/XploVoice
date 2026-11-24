# ADR-0004: Append-only, hash-chained audit log

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys · Status: accepted

**Decision.** `audit_log` is insert-only for the runtime role. Each row stores `event_hash = sha256(prev_hash ||
canonical event)`, chained per tenant (and one platform chain), with a transaction advisory lock per chain so
concurrent writers cannot fork it. Keys that could hold secrets or content (passwords, tokens, codes, transcripts) are
stripped before writing. Denied authorization decisions are audited too.

**Consequences.** Tampering with or deleting a row breaks the chain and is detectable. Off-host anchoring of chain heads
(WORM storage) is planned with M17 in Phase 7.
