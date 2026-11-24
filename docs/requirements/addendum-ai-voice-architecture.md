# MANDATORY ADDENDUM — DETAILED AI VOICE ARCHITECTURE

This section supplements the XploVoice HLD v1.3 and LLD v1.3. All requirements must be mapped to the approved LLD modules, database tables, APIs, security controls and acceptance criteria.

## A. Common AI Voice Engine

Build one reusable AI conversation engine for all communication channels.

The engine must not be duplicated for browser voice and telephone voice.

Communication channels must connect to the same agent orchestration, conversation context, business tools, knowledge base, security and billing services.

Support:
- Browser/WebRTC voice.
- PSTN telephone calls.
- SIP-based calls.
- Inbound and outbound calls.
- Future communication channels through adapters.

## B. Real-Time Voice Processing Pipeline

Implement the following streaming architecture:

Caller audio
→ Audio ingestion
→ Voice Activity Detection
→ Streaming Speech-to-Text
→ Partial and final transcript processing
→ Language identification
→ Conversation and agent context
→ LLM orchestration
→ Tenant-filtered RAG retrieval, when needed
→ Authorized tool execution, when needed
→ Streaming Text-to-Speech
→ Audio streaming to caller.

Requirements:
- Streaming rather than waiting for complete responses wherever supported.
- Partial transcript support.
- Voice activity detection.
- Silence detection and configurable timeouts.
- End-of-turn detection.
- Barge-in and interruption handling.
- Cancellation of obsolete speech generation after interruption.
- Conversation state management.
- Configurable speaking speed and voice settings where supported.
- Language switching.
- Provider timeout and fallback.
- Call disconnect and recovery handling.

## C. Voice Latency and Quality

Set an initial engineering target of p95 common-turn response latency below 1.5 seconds under a defined test workload.

Measure separately:
- Audio capture and ingestion.
- VAD and endpoint detection.
- STT partial and final results.
- LLM first-token latency.
- Tool execution latency.
- TTS first-audio latency.
- End-to-end first audible response.
- Full response completion.

Do not claim the target is achieved without benchmark evidence.

Build dashboards and load tests to measure latency by provider, model, language, region and call type.

## D. Telephony and SIP Provider Abstraction

Support multiple telephony providers through independent adapters.

The platform must not depend on one carrier or hard-code carrier-specific logic into the business layer.

Support:
- Customer-owned SIP trunks.
- XploVoice-managed number options where contractually available.
- DID and number management.
- Inbound routing.
- Outbound routing.
- SIP registration and authentication where applicable.
- SIP trunk configuration.
- LiveKit SIP integration.
- Call transfer.
- DTMF handling where required.
- Call status webhooks.
- Provider error handling.
- Provider health checks.
- Number and destination restrictions.
- Carrier-specific billing pulses and pricing units.

Provide provider selection and routing policies based on tenant configuration, country, availability, cost, reliability and approved provider capabilities.

Do not assume all providers support the same SIP features, countries, numbers, recording options or transfer mechanisms.

## E. Call Lifecycle Management

Implement a formal call state machine.

Cover:
- Initiated.
- Queued.
- Routing.
- Ringing.
- Answered.
- Connected.
- In progress.
- On hold, where supported.
- Transferring.
- Completed.
- Failed.
- Busy.
- No answer.
- Cancelled.
- Disconnected.

Maintain timestamps, provider identifiers, agent version, tenant, call direction, channel, usage events and terminal reason.

Handle duplicate, delayed and out-of-order provider events safely.

Use idempotent event processing.

## F. AI Agent Orchestration

The orchestration layer must manage:
- Agent identity and version.
- System instructions.
- Conversation state.
- Language.
- Model selection.
- STT and TTS selection.
- Knowledge-base access.
- Tool permissions.
- Call-level limits.
- Timeout and retry policies.
- Escalation rules.
- Human handoff.
- Session termination.

Use immutable agent versions or an equivalent versioning mechanism.

Every call must record the exact agent configuration version and provider/model versions used.

## G. RAG and Business Tool Execution

Implement tenant-isolated RAG and a controlled tool gateway.

Examples of tools:
- Check appointment availability.
- Book, reschedule or cancel appointments.
- Create or update leads.
- Retrieve CRM information.
- Create support tickets.
- Send approved notifications.
- Transfer calls.
- Retrieve approved business information.

Apply authorization before retrieval and before every tool action.

Validate tool inputs using schemas.

Support timeouts, idempotency, audit records, retry policies and human approval for sensitive actions.

Never allow unrestricted model-generated SQL, shell execution or arbitrary external requests.

## H. Native Business Workflows

Do not make XploVoice only a voice interface that depends on external applications for every business operation.

Provide reusable native workflow capabilities for:
- Appointment scheduling.
- Lead capture.
- Lead qualification.
- CRM activity.
- Customer follow-up.
- Campaign execution.
- Notifications.
- Business hours and holiday calendars.
- Human escalation.

External integrations should extend these workflows, not replace their core platform functionality.

## I. Inbound and Outbound Calling

Implement separate policies for inbound and outbound calls.

Inbound:
- Number-to-tenant mapping.
- Routing rules.
- Business hours.
- Agent selection.
- Welcome message.
- Queue and fallback.
- Human transfer.

Outbound:
- Authorized campaign configuration.
- Contact eligibility.
- Consent and suppression checks.
- Calling time windows.
- Country-specific restrictions.
- Rate and concurrency limits.
- Retry policies.
- Opt-out handling.
- Call outcome tracking.
- Audit history.

Do not implement unrestricted bulk calling. Apply applicable telecom, privacy, consent and marketing regulations.

## J. Worker and Queue Architecture

Separate the control plane from real-time voice processing.

Use:
- Modular monolith control plane.
- Independently deployable LiveKit voice workers.
- Background workers.
- Redis-backed queues where appropriate.
- Health checks.
- Worker heartbeats.
- Graceful shutdown.
- Job retry and dead-letter handling.
- Concurrency limits.
- Backpressure controls.
- Worker recovery.

Design for regional voice workers so India and US deployments can be supported without major architectural changes.

Do not introduce Kubernetes prematurely.

## K. Recording, Transcription and Consent

Support configurable recording and transcription policies.

Include:
- Recording enable/disable per tenant and agent.
- Consent announcement and capture where required.
- Recording access permissions.
- Secure private storage.
- Encryption.
- Retention schedules.
- Deletion workflows.
- Recording access audit.
- Transcript redaction and sensitive-data minimization where appropriate.

Respect country, state and customer-specific legal requirements.

Healthcare tenants must follow the dedicated healthcare policy and vendor eligibility gates in M19–M25.

## L. Failover and Reliability

Implement:
- STT provider fallback.
- LLM provider fallback.
- TTS provider fallback.
- Telephony routing fallback where supported.
- Circuit breakers.
- Exponential backoff with jitter.
- Timeouts.
- Idempotency.
- Retry limits.
- Graceful degradation.
- Call failure handling.
- Human fallback.

Never retry a consequential business action without checking idempotency and execution status.

## M. Concurrency and Capacity Management

Implement:
- Tenant-level concurrent call limits.
- Plan-level concurrency limits.
- Platform-wide capacity controls.
- Provider rate limits.
- Worker capacity tracking.
- Queue depth monitoring.
- Admission control.
- Usage and spending limits.
- Overload protection.

Provide capacity metrics for active calls, queued calls, worker utilization, provider usage and failure rates.

## N. Observability and Operational Monitoring

Every call must be traceable across:
- Telephony provider.
- SIP session.
- LiveKit room.
- Voice worker.
- STT request.
- LLM request.
- Tool execution.
- TTS request.
- Billing event.

Use correlation IDs and distributed tracing.

Monitor:
- Call connection success.
- Call completion.
- First-response latency.
- Turn latency.
- STT errors.
- LLM errors.
- TTS errors.
- Provider availability.
- Transfer success.
- Call quality.
- Cost per call and minute.
- Worker health.
- Queue depth.
- Tenant usage.

Avoid logging secrets or unnecessary sensitive conversation data.

## O. Architecture Performance and Acceptance Gates

The following must be validated through automated and controlled testing:

1. Browser voice conversation works end to end.
2. Telephone inbound conversation works end to end.
3. Telephone outbound conversation works end to end with approved consent controls.
4. Partial transcripts and streaming audio work.
5. Barge-in interrupts ongoing speech correctly.
6. RAG retrieves only authorized tenant data.
7. Tools execute only with valid permissions.
8. Human transfer and escalation work.
9. Provider failure does not silently corrupt call state.
10. Duplicate webhooks do not create duplicate actions or billing.
11. Tenant concurrency and platform limits are enforced.
12. Usage is recorded against actual provider units.
13. Call recordings follow configured consent and retention policies.
14. Voice workers recover from failures.
15. Latency targets are measured and reported.
16. All critical tenant-isolation and security tests pass.

## P. Module-Wise Vertical-Slice Delivery

Implement every module as a complete vertical slice.

A module is not complete merely because its frontend page or backend endpoints exist.

Each module must include:
- Requirements mapping.
- Database migrations.
- Backend business logic.
- API endpoints.
- Frontend screens and interactions.
- Authentication and authorization.
- Tenant isolation.
- Security validation.
- Unit tests.
- Integration tests.
- API documentation.
- Monitoring and audit events.
- Acceptance criteria.
- Demonstrable working functionality.

Maintain a module dependency graph and an implementation status register.

Do not move to a dependent module until its required acceptance gates are satisfied.

## Q. Country and Language Configuration

Initial supported markets:
- India.
- United States.

Initial language capabilities:
- Hindi.
- Hinglish.
- Indian English.
- US English.

Keep country, currency, timezone, number format, carrier selection, language, consent rules and regulatory policies configurable.

Initial currencies:
- INR.
- USD.

Use UTC timestamps internally and tenant IANA time zones for business operations.

Use E.164 phone-number representation.

## R. Non-Negotiable Architecture Constraints

- Follow approved HLD and LLD.
- One common voice engine for all channels.
- Multiple SIP providers through adapters.
- Hybrid cloud and open-source AI.
- Tenant isolation at every data and execution boundary.
- Modular monolith control plane.
- Independently deployable real-time voice workers.
- Docker-based initial deployment on Ubuntu VPS.
- No unnecessary microservices or premature Kubernetes.
- No real PHI in development.
- No unapproved PHI transmission.
- No unsupported HIPAA compliance claims.
- No fake integrations or fabricated provider capabilities.
- No production-readiness claims without acceptance evidence.

Map these requirements to the existing official LLD module IDs. If any requirement is missing from the LLD, raise a documented architecture change request rather than silently ignoring it.