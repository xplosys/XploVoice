# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""PHI classification and minimization (M20, LLD v1.3 section 3 PHIClassificationService).

`redact` replaces common identifiers in free text with a label, so text can leave a healthcare organisation's
protected records (webhook payloads, incident summaries, the platform's own views) without carrying them. It is a
pattern-based safety net, not a de-identification method: names and free-form clinical details are not reliably
found by patterns, which is why PHI-bearing records (transcripts, callers' numbers) are also withheld by
permission rather than only redacted.

`DEFAULT_INVENTORY` is the starting classification of each kind of record. Locked entries always hold PHI."""

import re
from typing import Any

# Order matters: the more specific patterns run first.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("MRN", re.compile(r"\b(?:MRN|medical record(?: number)?|patient id|member id)\s*[:#]?\s*[A-Za-z0-9-]{4,}", re.I)),
    ("DATE", re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-](?:\d{4}|\d{2})|\d{4}-\d{2}-\d{2})\b")),
    ("PHONE", re.compile(r"(?<![\w])\+?\d[\d ().-]{7,}\d\b")),
    ("NUMBER", re.compile(r"\b\d{6,}\b")),
    (
        "ADDRESS",
        re.compile(
            r"\b\d{1,6}\s+(?:[A-Z][a-z]+\s+){1,3}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|"
            r"Court|Ct|Way)\b\.?",
        ),
    ),
)

DEFAULT_INVENTORY: tuple[tuple[str, str, bool, str], ...] = (
    # resource type, classification, locked, note
    ("call_transcript", "phi", True, "What callers and the agent said."),
    ("caller_number", "phi", True, "The other party's phone number on a call."),
    ("call_recording", "phi", True, "Recordings (storage awaiting configuration)."),
    ("tool_payload", "phi", True, "What a business tool was asked and returned during a call."),
    ("appointment", "phi", True, "Bookings name a person and a time with your organisation."),
    ("lead", "phi", False, "Contact details and notes from calls."),
    ("ticket", "phi", False, "Messages and escalations taken on calls."),
    ("follow_up", "phi", False, "Reminders to contact a person."),
    ("consent_record", "phi", False, "A number with its consent to be called or recorded."),
    ("knowledge_document", "review", False, "Reference documents should hold no patient information."),
    ("agent_configuration", "not_phi", False, "Prompts and settings; keep patient information out of them."),
    ("analytics", "not_phi", False, "Counts and durations only."),
)


def redact(value: str) -> tuple[str, list[str]]:
    """Returns the text with identifiers replaced by `[LABEL]`, and the labels found."""
    found: list[str] = []
    out = value
    for label, pattern in PATTERNS:
        out, n = pattern.subn(f"[{label}]", out)
        if n:
            found.append(label)
    return out, found


# Fields kept as they are in a minimized event: identifiers of XploVoice records, types, statuses and times.
SAFE_KEYS = frozenset(
    {
        "id",
        "type",
        "status",
        "state",
        "kind",
        "event",
        "occurred_at",
        "created_at",
        "updated_at",
        "starts_at",
        "ends_at",
        "start",
        "end",
        "calendar_id",
        "appointment_id",
        "lead_id",
        "ticket_id",
        "follow_up_id",
        "call_id",
        "agent_id",
        "invoice_id",
        "priority",
        "score",
        "source",
        "channel",
        "currency",
        "amount",
        "total",
        "due_at",
        "paid_at",
        "period_start",
        "period_end",
        "meter",
        "threshold",
        "reason_code",
    }
)


def minimize(payload: Any) -> Any:
    """A copy of an event payload for a healthcare organisation's webhooks: identifiers, statuses and times stay;
    every other value is withheld (`"[withheld]"`); nested objects are minimized the same way. The receiver
    fetches details through the API, where permission checks and the PHI access log apply."""
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for k, v in payload.items():
            if isinstance(v, dict | list):
                out[k] = minimize(v)
            elif k in SAFE_KEYS or k.endswith("_id") or v is None or isinstance(v, bool):
                out[k] = v
            else:
                out[k] = "[withheld]"
        return out
    if isinstance(payload, list):
        return [minimize(v) for v in payload]
    return "[withheld]"


def mask_number(number: str | None) -> str | None:
    """`+1•••••••4567`: enough to tell calls apart, not to call the person."""
    if not number:
        return number
    return number[:2] + "•" * max(0, len(number) - 6) + number[-4:]
