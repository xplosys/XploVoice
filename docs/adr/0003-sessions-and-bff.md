# ADR-0003: Token sessions behind a backend-for-frontend

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys · Status: accepted

**Decision.**
- The API issues 15-minute HS256 access tokens and opaque refresh tokens. Only an HMAC of a refresh token is stored.
- Refresh rotates the token; reuse of a rotated token revokes the whole family.
- Every request checks that the token's session family is still live, so logout, removal and suspension take effect
  immediately.
- The Next.js server holds both tokens in `httpOnly`, `SameSite=Lax` cookies and calls the API server-side. Browser
  JavaScript never sees a token. Middleware refreshes the access token before protected pages render.

**Consequences.** XSS cannot read tokens. The API stays usable by other clients with bearer tokens. HS256 will move to
asymmetric keys from the secrets manager before production (tracked for Phase 9 hardening).
