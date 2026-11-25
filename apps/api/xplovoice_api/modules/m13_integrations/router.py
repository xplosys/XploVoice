# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Integrations (M13). External systems extend the native workflows; they never replace them (addendum H).

Signed webhooks work now. The CRM and calendar connectors are listed but awaiting configuration: each needs an
XploVoice developer account and OAuth client registered with the vendor (Phase 0, section N)."""

import secrets
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from ...core.context import Ctx, require
from ...core.errors import bad_request, not_found
from ...core.permissions import Perm
from ...core.security import encrypt_secret
from .dispatch import UnsafeUrlError, check_url
from .events import EVENT_TYPES
from .models import Integration, IntegrationEvent, WebhookDelivery

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])

CATALOG = [
    {
        "provider": "webhook",
        "name": "Webhooks",
        "category": "Developer",
        "description": "Send signed events (bookings, leads, tickets) to your own HTTPS endpoint.",
        "status": "available",
    },
    {
        "provider": "hubspot",
        "name": "HubSpot",
        "category": "CRM",
        "description": "Sync leads and call activity to HubSpot.",
        "status": "awaiting_configuration",
    },
    {
        "provider": "salesforce",
        "name": "Salesforce",
        "category": "CRM",
        "description": "Sync leads and call activity to Salesforce.",
        "status": "awaiting_configuration",
    },
    {
        "provider": "google_calendar",
        "name": "Google Calendar",
        "category": "Calendar",
        "description": "Mirror bookings to a Google calendar.",
        "status": "awaiting_configuration",
    },
    {
        "provider": "microsoft_365",
        "name": "Microsoft 365",
        "category": "Calendar",
        "description": "Mirror bookings to an Outlook calendar.",
        "status": "awaiting_configuration",
    },
]
NOTE = "Needs an XploVoice developer account and OAuth client registered with the vendor (awaiting configuration)."


class CatalogOut(BaseModel):
    provider: str
    name: str
    category: str
    description: str
    status: str
    note: str | None


class WebhookIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=10, max_length=500)
    events: list[str] = Field(default_factory=list, max_length=len(EVENT_TYPES))

    @field_validator("events")
    @classmethod
    def _events(cls, v: list[str]) -> list[str]:
        bad = [e for e in v if e not in EVENT_TYPES]
        if bad:
            raise ValueError(f"Unknown event {bad[0]}")
        return list(dict.fromkeys(v))


class WebhookPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    events: list[str] | None = None
    status: Literal["active", "disabled"] | None = None

    @field_validator("events")
    @classmethod
    def _events(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else WebhookIn._events(v)


class IntegrationOut(BaseModel):
    id: UUID
    provider: str
    name: str
    status: str
    url: str | None
    events: list[str]
    created_at: datetime
    secret: str | None = None  # returned once, when created or rotated


class DeliveryOut(BaseModel):
    id: int
    event_type: str
    status: str
    attempts: int
    last_status: int | None
    last_error: str | None
    next_attempt_at: datetime
    created_at: datetime


def _out(i: Integration, secret: str | None = None) -> IntegrationOut:
    return IntegrationOut(
        id=i.id,
        provider=i.provider,
        name=i.name,
        status=i.status,
        url=i.settings.get("url"),
        events=list(i.events or []),
        created_at=i.created_at,
        secret=secret,
    )


def _get(ctx: Ctx, iid: UUID) -> Integration:
    i = ctx.session.scalar(select(Integration).where(Integration.id == iid, Integration.tenant_id == ctx.tenant.id))
    if not i:
        raise not_found()
    return i


@router.get("/catalog", response_model=list[CatalogOut])
def catalog(ctx: Ctx = Depends(require(Perm.TENANT_READ))) -> list[CatalogOut]:
    return [CatalogOut(**c, note=NOTE if c["status"] == "awaiting_configuration" else None) for c in CATALOG]


@router.get("/events")
def event_types(ctx: Ctx = Depends(require(Perm.TENANT_READ))) -> list[str]:
    return list(EVENT_TYPES)


@router.get("", response_model=list[IntegrationOut])
def list_integrations(ctx: Ctx = Depends(require(Perm.TENANT_READ))) -> list[IntegrationOut]:
    return [_out(i) for i in ctx.session.scalars(select(Integration).order_by(Integration.created_at))]


@router.post("/webhooks", response_model=IntegrationOut, status_code=status.HTTP_201_CREATED)
def create_webhook(data: WebhookIn, ctx: Ctx = Depends(require(Perm.INTEGRATIONS_MANAGE))) -> IntegrationOut:
    try:
        url = check_url(data.url.strip())
    except UnsafeUrlError as e:
        raise bad_request("unsafe_url", str(e)) from None
    secret = "whsec_" + secrets.token_urlsafe(32)
    i = Integration(
        tenant_id=ctx.tenant.id,
        provider="webhook",
        name=data.name.strip(),
        status="active",
        settings={"url": url},
        events=data.events,
        secret_ciphertext=encrypt_secret(secret),
        created_by_membership_id=ctx.membership.id,
    )
    ctx.session.add(i)
    ctx.session.flush()
    ctx.audit("integration.created", resource_type="integration", resource_id=str(i.id), provider="webhook")
    ctx.session.refresh(i)
    return _out(i, secret)


@router.patch("/{iid}", response_model=IntegrationOut)
def update_integration(
    iid: UUID, data: WebhookPatch, ctx: Ctx = Depends(require(Perm.INTEGRATIONS_MANAGE))
) -> IntegrationOut:
    i = _get(ctx, iid)
    if data.name:
        i.name = data.name.strip()
    if data.events is not None:
        i.events = data.events
    if data.status:
        i.status = data.status
    ctx.session.flush()
    ctx.audit("integration.updated", resource_type="integration", resource_id=str(i.id), status=i.status)
    ctx.session.refresh(i)
    return _out(i)


@router.post("/{iid}/rotate-secret", response_model=IntegrationOut)
def rotate(iid: UUID, ctx: Ctx = Depends(require(Perm.INTEGRATIONS_MANAGE))) -> IntegrationOut:
    i = _get(ctx, iid)
    secret = "whsec_" + secrets.token_urlsafe(32)
    i.secret_ciphertext = encrypt_secret(secret)
    ctx.audit("integration.secret_rotated", resource_type="integration", resource_id=str(i.id))
    return _out(i, secret)


@router.get("/{iid}/deliveries", response_model=list[DeliveryOut])
def deliveries(iid: UUID, ctx: Ctx = Depends(require(Perm.TENANT_READ))) -> list[DeliveryOut]:
    i = _get(ctx, iid)
    rows = ctx.session.execute(
        select(WebhookDelivery, IntegrationEvent.type)
        .join(IntegrationEvent, IntegrationEvent.id == WebhookDelivery.event_id)
        .where(WebhookDelivery.integration_id == i.id)
        .order_by(WebhookDelivery.id.desc())
        .limit(100)
    ).all()
    return [
        DeliveryOut(
            id=d.id,
            event_type=t,
            status=d.status,
            attempts=d.attempts,
            last_status=d.last_status,
            last_error=d.last_error,
            next_attempt_at=d.next_attempt_at,
            created_at=d.created_at,
        )
        for d, t in rows
    ]
