# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Domain events for integrations (M13): a transactional outbox. A workflow writes its change and the event in the
same transaction, and one delivery row per subscribed webhook, so an event is never sent for a change that rolled
back and never lost for one that committed. The dispatcher (dispatch.py) delivers them."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Integration, IntegrationEvent, WebhookDelivery

EVENT_TYPES = (
    "appointment.booked",
    "appointment.rescheduled",
    "appointment.cancelled",
    "lead.created",
    "lead.updated",
    "ticket.created",
    "ticket.updated",
    "follow_up.created",
    "billing.alert",
    "invoice.issued",
    "invoice.paid",
)


def emit(session: Session, tenant_id: UUID, type_: str, payload: dict[str, Any]) -> int:
    """In a healthcare organisation the payload is minimized first (M20): webhook receivers are outside the
    organisation's BAA chain, so they get ids, statuses and times, and fetch details through the API."""
    from ..m19_healthcare.mode import phi_mode
    from ..m20_phi.classify import minimize

    assert type_ in EVENT_TYPES, type_
    if phi_mode(session):
        payload = minimize(payload)
    ev = IntegrationEvent(tenant_id=tenant_id, type=type_, payload=payload)
    session.add(ev)
    session.flush()
    hooks = session.scalars(
        select(Integration).where(Integration.provider == "webhook", Integration.status == "active")
    ).all()
    for h in hooks:
        if not h.events or type_ in h.events:
            session.add(WebhookDelivery(tenant_id=tenant_id, event_id=ev.id, integration_id=h.id))
    return ev.id
