# ADR-0008: Knowledge retrieval, the tool gateway and outbound integrations

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys · Status: accepted for development

**Context.** Phase 5 adds M11 (workflows), M12 (knowledge base), M13 (integrations) and M14 (support and
notifications), plus tools and retrieval in the conversation engine. The addendum asks for retrieval that reads only
the caller's tenant (G), a controlled tool gateway (G) and native workflows (H). The Phase 5 exit gates are O6
("RAG retrieves only authorized tenant data") and O7 ("Tools execute only with valid permissions"). No document
names an embedding vendor, a scanning service or a messaging provider.

**Decision.**

**Retrieval (M12)**
- Search uses PostgreSQL full-text search: each chunk stores a generated `tsvector` (English stemming plus a
  `simple` dictionary so Hindi and Hinglish words still match), with a GIN index, ranked by `ts_rank_cd`.
  Embeddings need a vendor that is awaiting configuration and the pgvector extension, which is not in the base
  image. The search function is the only place to change when they arrive.
- A query searches only the knowledge bases granted on the agent version, only if active, only documents that are
  ready, and runs under the call's tenant context with FORCE RLS. A tenant id is never taken from the request.
- Passages go to the model in a separate system message that says they are reference data, not instructions.
- Uploads (PDF, Word, text, Markdown, CSV up to 5 MB) are typed by content, not by name. Every file is scanned
  before a document row exists: ClamAV when `XV_CLAMAV_URL` is set, otherwise a built-in check (EICAR,
  executables) that is allowed only in development and test. Production-like environments without ClamAV refuse
  uploads (503). Only extracted text is kept, never the original file.

**Tool gateway (M09 tools)**
- Models call tools natively (OpenAI and Anthropic tool calling; the mock adapter chooses tools by keyword for
  tests). The server runs the loop: at most 3 rounds and 4 calls per round per turn.
- Every call passes, in order: granted on the version, switched on in the tenant's policy, prerequisites met (for
  example a booking calendar), strict input validation (unknown fields refused), idempotency (one execution per
  request key), and approval. Sensitive tools (cancel by default) wait as `pending_approval` until a person with
  `tools:approve` approves; approving claims the row so it runs once.
- Each tool runs in its own transaction with a statement timeout and an overall timeout, with one retry on a
  database error. Every use writes a `tool_executions` row, an audit event and metrics. Failures are returned to
  the model as a short error, never raised into the call.
- Tools act only on records of the tenant, and contact details come from the record (for example the booking's
  phone), never from a number the model invents.

**Workflows, tickets and notifications (M11, M14)**
- Bookings lock the calendar row and rely on a partial unique index on (calendar, start) for booked slots, so two
  callers cannot take the same slot. Org-wide holidays close every calendar and every agent's business hours.
- An escalation on a call creates exactly one high-priority ticket per call (partial unique index).
- Messages are sent only from admin-approved templates with fixed placeholders. With no SMS or email provider
  configured, messages are stored as `held` with the reason and never reported as sent.

**Integrations (M13)**
- Domain events are written to a transactional outbox in the same transaction as the change. A dispatcher in each
  API process claims due deliveries with `SKIP LOCKED` through a SECURITY DEFINER function, signs each request
  (`X-XploVoice-Signature: t=..,v1=HMAC-SHA256("t.body")`), sends an idempotency id, backs off exponentially and
  marks a delivery dead after 8 attempts.
- Webhook URLs must be https on port 443 or 8443, with no credentials, and must resolve only to public addresses.
  Redirects are not followed. The check runs when the webhook is saved and again before each delivery.
- CRM and calendar connectors (HubSpot, Salesforce, Google, Microsoft) need OAuth clients registered with each
  vendor and are listed as awaiting configuration.

**Consequences.**
- Keyword search misses paraphrases that embeddings would catch. Acceptable until a vendor is configured.
- DNS can change between the check and the connection (TOCTOU). The window is small and redirects are off. Pinning
  the resolved address in the HTTP connection is a follow-up before production.
- Approval adds a delay for sensitive actions: the agent tells the caller the request is passed on.
