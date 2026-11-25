# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Support tickets and approved notifications (M14).

Notifications: an agent can only send a template an admin approved, filled with a fixed set of placeholders, to
the contact on the record it is about (never a number the model makes up). Delivery needs an SMS or email
provider account; none is configured yet, so messages are kept with status "held" and the reason, never reported
as sent (awaiting configuration)."""

import re
import string
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..m11_workflows.service import Actor, WorkflowError, phone, reference
from ..m13_integrations.events import emit
from .models import Notification, NotificationTemplate, Ticket, TicketComment

PLACEHOLDERS = ("customer_name", "reference", "date_time", "business_name")
DELIVERY_PROVIDERS: dict[str, str | None] = {"sms": None, "email": None}  # awaiting configuration


def template_fields(body: str) -> set[str]:
    try:
        return {f for _, f, _, _ in string.Formatter().parse(body) if f is not None}
    except ValueError:
        raise WorkflowError("invalid_template", "Braces must wrap a placeholder name, like {customer_name}.") from None


def check_template(body: str) -> None:
    unknown = template_fields(body) - set(PLACEHOLDERS)
    if unknown:
        raise WorkflowError(
            "invalid_template",
            f"Unknown placeholder {{{sorted(unknown)[0]}}}. Use: " + ", ".join(f"{{{p}}}" for p in PLACEHOLDERS),
        )


def render(body: str, values: dict[str, str]) -> str:
    return body.format_map({p: values.get(p, "") for p in PLACEHOLDERS})


def ticket_payload(t: Ticket) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "reference": t.reference,
        "subject": t.subject,
        "priority": t.priority,
        "status": t.status,
        "source": t.source,
    }


def create_ticket(
    session: Session,
    actor: Actor,
    *,
    subject: str,
    description: str = "",
    priority: str = "normal",
    name: str = "",
    phone_number: str | None = None,
    email: str | None = None,
    source: str | None = None,
) -> Ticket:
    t = Ticket(
        tenant_id=actor.tenant_id,
        reference=reference("T"),
        subject=re.sub(r"\s+", " ", subject).strip()[:200] or "Request from a caller",
        description=description[:4000],
        priority=priority,
        requester_name=name[:120],
        requester_phone=phone(phone_number, actor.country),
        requester_email=(email or None) and email.strip()[:200],
        source=source or actor.source,
        call_id=actor.call_id,
        created_by_membership_id=actor.membership_id,
    )
    session.add(t)
    session.flush()
    emit(session, actor.tenant_id, "ticket.created", ticket_payload(t))
    return t


def escalation_ticket(session: Session, actor: Actor, *, trigger: str, action: str, summary: str) -> Ticket | None:
    """One ticket per escalated call, so a recovered worker resending the event never makes a second one."""
    assert actor.call_id is not None
    if session.scalar(select(Ticket.id).where(Ticket.call_id == actor.call_id, Ticket.source == "escalation")):
        return None
    with session.begin_nested():
        return create_ticket(
            session,
            actor,
            subject="Caller asked for a person" if trigger != "unclear" else "Agent couldn't understand the caller",
            description=f"Escalation on a call (trigger: {trigger}; action: {action}).\n\n{summary}".strip(),
            priority="high",
            source="escalation",
        )


def comment(session: Session, actor: Actor, t: Ticket, body: str, internal: bool = True) -> TicketComment:
    c = TicketComment(
        tenant_id=actor.tenant_id,
        ticket_id=t.id,
        body=body[:4000],
        internal=internal,
        author_membership_id=actor.membership_id,
    )
    session.add(c)
    session.flush()
    return c


def set_status(t: Ticket, status: str) -> None:
    t.status = status
    t.resolved_at = datetime.now(UTC) if status in ("resolved", "closed") else None


def send(
    session: Session,
    actor: Actor,
    *,
    key: str,
    channel: str,
    recipient: str,
    values: dict[str, str],
    idempotency_key: str,
    related_type: str | None = None,
    related_id: UUID | None = None,
) -> Notification:
    """Queues one message from an approved template. Idempotent per key."""
    existing = session.scalar(select(Notification).where(Notification.idempotency_key == idempotency_key))
    if existing:
        return existing
    tpl = session.scalar(
        select(NotificationTemplate).where(
            NotificationTemplate.key == key,
            NotificationTemplate.channel == channel,
            NotificationTemplate.status == "approved",
        )
    )
    if not tpl:
        raise WorkflowError("no_template", f"No approved {channel} message called {key} exists.")
    to = phone(recipient, actor.country) if channel == "sms" else recipient.strip()
    if not to:
        raise WorkflowError("no_recipient", "There's no contact to send the message to.")
    provider = DELIVERY_PROVIDERS.get(channel)
    n = Notification(
        tenant_id=actor.tenant_id,
        template_id=tpl.id,
        channel=channel,
        recipient=to,
        body=render(tpl.body, values),
        status="queued" if provider else "held",
        status_reason=None
        if provider
        else f"No {channel.upper()} provider is configured yet (awaiting configuration).",
        related_type=related_type,
        related_id=related_id,
        call_id=actor.call_id,
        idempotency_key=idempotency_key,
    )
    session.add(n)
    session.flush()
    return n
