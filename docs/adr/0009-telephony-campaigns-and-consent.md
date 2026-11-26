# ADR-0009: Telephony, outbound campaigns, the policy engine and consent

**Xplosys** · Copyright © 2026 Xplosys. All rights reserved. · Confidential – Proprietary to Xplosys · Status: accepted for development

**Context.** Phase 6 adds M04 (carriers, trunks, numbers), M06 (inbound routing and queues), M07 (outbound
campaigns) and M22-core (consent and do-not-call, split from M22 by CR-023). The addendum asks for a carrier
abstraction with LiveKit SIP (D), the 15-state call lifecycle with idempotent, order-tolerant events (E), and inbound
and outbound rules (I), with "no unrestricted bulk calling". No document names a carrier, and no carrier contract
exists (Phase 0 section N), so no vendor is named and "numbers from XploVoice" is awaiting configuration.

**Decision.**

**Carriers (M04)**
- Adapters implement one contract (`m04_telephony/adapters/base.py`): sync trunk, delete trunk, place call, transfer,
  hang up. The business layer never contains carrier-specific logic.
- `sip`: the customer's own SIP trunk through the LiveKit Twirp API. Inbound: an inbound trunk with the trunk's
  numbers and allowed source addresses, and a dispatch rule that puts each caller in a new room `xvin_<random>`.
  Outbound: an outbound trunk, and `CreateSIPParticipant` with `wait_until_answered` per call. Transfer is SIP REFER
  (`TransferSIPParticipant`, cold only). Final SIP codes map to outcomes: 486/600/603 busy, 408/480/487 no answer,
  others failed. Each request carries a 60-second token with only the grants it needs.
- `simulated`: development and tests only, refused when the environment is production-like. The last digit of the
  number called picks the outcome (2 busy, 3 no answer, 4 failed), and its status events use the same verified
  webhook path as a real carrier.
- `managed` (numbers bought from XploVoice): awaiting configuration until a carrier is contracted.
- Trunk passwords are Fernet-encrypted and never returned. Billing pulses are a trunk capability; usage is stored
  in billed seconds (rounded up to the pulse) per answered call. Nothing is priced (Phase 7, awaiting configuration).
- A number is unique across all organisations while active. The conflict message never says who has it.

**Call lifecycle (M08, CR-003)**
- Two linked state machines: `status` (the voice session, Phase 3) and `state` (the 15 states of addendum E).
  Engine moves update the state through a fixed mapping; carrier events update the state directly. A late or
  repeated update never moves a call backwards, and a terminal state never changes. The only loops allowed are
  in progress, on hold and transferring. Every accepted change is written to `call_state_transitions`.
- Carrier events are verified first (LiveKit: JWT signed with the API secret carrying the body's SHA-256; simulated:
  HMAC with a timestamp window), then stored once per (provider, event id) in `call_provider_events` before they
  may change a call. An event that no longer applies is kept with `applied = false`.
- Calls are found from carrier events by provider references (call, participant, SIP call id, room) through
  definer functions that return ids only.

**Inbound (M06)**
- A definer function maps the dialled number to its organisation. The route names an agent, an optional queue and a
  fallback (a short spoken message then hang up, or hang up).
- Paused telephony (organisation kill switch or platform flag) or no route: hang up. Agent not published: fallback.
  Organisation call limit reached: queue if the route has one with room, otherwise fallback. Queued callers are
  connected oldest first as soon as a slot frees up, or get the fallback after the queue's longest wait. Queue
  hold audio is not played.

**Outbound (M07) and the policy engine**
- A campaign is a draft until someone with `campaigns:approve` approves it, and another person must approve when
  the organisation has one. Any edit or new contacts send it back to draft.
- Before every call, the policy engine evaluates and stores every check (`policy_decisions`):
  block: platform switch, organisation switch, valid number, country allowed, premium-rate or shared-cost number,
  do-not-call list, consent, attempts left; defer: campaign not running, calling window, organisation concurrency,
  campaign concurrency, calls per minute, daily outbound minutes. Only an allowed call reaches the carrier.
  Transfers go through the destination checks too.
- Calling window: the campaign's window, never wider than a country default (India 09:00–21:00, US 08:00–21:00),
  in the person's local time (the contact's time zone, else every zone the number may be in, else the campaign's).
  These defaults are a starting point from common guidance, not legal advice: the Phase 0 legal review is open.
- The dialer runs in each API process. Due contacts are listed through a definer function, then each is claimed
  with `SKIP LOCKED` under its own tenant, so several processes can run it. Retry: answered completes the contact;
  otherwise retry after the campaign's interval, or exhausted after the last attempt.

**Consent and do-not-call (M22-core)**
- A campaign may call only with a granted, unrevoked consent for outbound calls, never while the number is on the
  organisation's do-not-call list. Records are never deleted: revoking and removing keep who, when and why.
  Removing a number from the list needs approve rights, and after an opt-out a real reason.
- "Stop calling me" (and similar phrases, including Hinglish) on any phone call puts the number on the list,
  revokes consent and stops every open campaign contact for it, at once.
- Recording: the agent's notice is said first and cannot be talked over. With "ask the caller first", the answer is
  stored as a consent record. Storing audio (LiveKit egress and storage) is awaiting configuration.

**Engine (M09)** adds, for phone calls only: transfer to the agent's first transfer number (numbers never leave
the server; the worker refers to them by position), opt-out, keypad tones (0 asks for a person; other keys are sent
as a typed reply after # or a pause), the recording notice and consent answer, and the fallback message mode.

**Consequences.**
- Real PSTN calls in India and the US need the customer's carrier trunk and a LiveKit server with SIP. Until a
  carrier is contracted, the Phase 6 gate "real PSTN inbound and outbound" can be shown only with a customer trunk.
- Warm transfer, hold music, call recording storage, the national do-not-call registry lookups and the legal review
  of calling windows remain open.
