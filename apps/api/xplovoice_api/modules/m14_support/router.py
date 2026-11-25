# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Support tickets and notifications API (M14)."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...core.context import Ctx, require
from ...core.errors import bad_request, conflict, not_found
from ...core.permissions import Perm
from ..m11_workflows.service import Actor, WorkflowError
from ..m13_integrations.events import emit
from . import service as svc
from .models import Notification, NotificationTemplate, Ticket, TicketComment

router = APIRouter(tags=["support"])


def _actor(ctx: Ctx) -> Actor:
    return Actor(
        tenant_id=ctx.tenant.id, country=ctx.tenant.country_code, source="manual", membership_id=ctx.membership.id
    )


# ---------------------------------------------------------------------------------------------------- tickets
class TicketIn(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    requester_name: str = Field(default="", max_length=120)
    requester_phone: str | None = Field(default=None, max_length=30)
    requester_email: str | None = Field(default=None, max_length=200)


class TicketPatch(BaseModel):
    status: Literal["open", "pending", "resolved", "closed"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    assignee_membership_id: UUID | None = None


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class CommentOut(BaseModel):
    body: str
    internal: bool
    author_membership_id: UUID | None
    created_at: datetime


class TicketOut(BaseModel):
    id: UUID
    reference: str
    subject: str
    description: str
    priority: str
    status: str
    requester_name: str
    requester_phone: str | None
    requester_email: str | None
    source: str
    call_id: UUID | None
    assignee_membership_id: UUID | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class TicketDetail(TicketOut):
    comments: list[CommentOut]


def _ticket(ctx: Ctx, ticket_id: UUID) -> Ticket:
    t = ctx.session.scalar(select(Ticket).where(Ticket.id == ticket_id, Ticket.tenant_id == ctx.tenant.id))
    if not t:
        raise not_found()
    return t


def _out(t: Ticket) -> TicketOut:
    return TicketOut.model_validate(t, from_attributes=True)


@router.get("/v1/tickets", response_model=list[TicketOut])
def list_tickets(
    status_: str | None = Query(default=None, alias="status"),
    call_id: UUID | None = None,
    ctx: Ctx = Depends(require(Perm.SUPPORT_READ)),
) -> list[TicketOut]:
    q = select(Ticket)
    if status_ == "active":
        q = q.where(Ticket.status.in_(("open", "pending")))
    elif status_:
        q = q.where(Ticket.status == status_)
    if call_id:
        q = q.where(Ticket.call_id == call_id)
    return [_out(t) for t in ctx.session.scalars(q.order_by(Ticket.created_at.desc()).limit(500))]


@router.post("/v1/tickets", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(data: TicketIn, ctx: Ctx = Depends(require(Perm.SUPPORT_MANAGE))) -> TicketOut:
    try:
        t = svc.create_ticket(
            ctx.session,
            _actor(ctx),
            subject=data.subject,
            description=data.description,
            priority=data.priority,
            name=data.requester_name,
            phone_number=data.requester_phone,
            email=data.requester_email,
        )
    except WorkflowError as e:
        raise bad_request(e.code, e.message) from None
    ctx.audit("ticket.created", resource_type="ticket", resource_id=str(t.id))
    ctx.session.refresh(t)
    return _out(t)


@router.get("/v1/tickets/{ticket_id}", response_model=TicketDetail)
def read_ticket(ticket_id: UUID, ctx: Ctx = Depends(require(Perm.SUPPORT_READ))) -> TicketDetail:
    t = _ticket(ctx, ticket_id)
    cs = ctx.session.scalars(select(TicketComment).where(TicketComment.ticket_id == t.id).order_by(TicketComment.id))
    return TicketDetail(
        **_out(t).model_dump(), comments=[CommentOut.model_validate(c, from_attributes=True) for c in cs]
    )


@router.patch("/v1/tickets/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: UUID, data: TicketPatch, ctx: Ctx = Depends(require(Perm.SUPPORT_MANAGE))) -> TicketOut:
    t = _ticket(ctx, ticket_id)
    changes = {}
    if data.status and data.status != t.status:
        changes["status"] = f"{t.status} → {data.status}"
        svc.set_status(t, data.status)
    if data.priority and data.priority != t.priority:
        changes["priority"] = f"{t.priority} → {data.priority}"
        t.priority = data.priority
    if data.assignee_membership_id:
        t.assignee_membership_id = data.assignee_membership_id
        changes["assignee"] = "changed"
    if changes:
        svc.comment(ctx.session, _actor(ctx), t, "; ".join(f"{k}: {v}" for k, v in changes.items()))
        emit(ctx.session, ctx.tenant.id, "ticket.updated", svc.ticket_payload(t))
    ctx.session.flush()
    ctx.audit("ticket.updated", resource_type="ticket", resource_id=str(t.id), **changes)
    ctx.session.refresh(t)
    return _out(t)


@router.post("/v1/tickets/{ticket_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(ticket_id: UUID, data: CommentIn, ctx: Ctx = Depends(require(Perm.SUPPORT_MANAGE))) -> CommentOut:
    t = _ticket(ctx, ticket_id)
    c = svc.comment(ctx.session, _actor(ctx), t, data.body)
    t.updated_at = datetime.now(UTC)
    ctx.session.refresh(c)
    return CommentOut.model_validate(c, from_attributes=True)


# ---------------------------------------------------------------------------------------------------- templates
class TemplateIn(BaseModel):
    key: str = Field(pattern=r"^[a-z_]{2,40}$")
    name: str = Field(min_length=1, max_length=120)
    channel: Literal["sms", "email"]
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=1, max_length=1000)


class TemplatePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=1000)
    status: Literal["draft", "approved", "retired"] | None = None


class TemplateOut(BaseModel):
    id: UUID
    key: str
    name: str
    channel: str
    subject: str | None
    body: str
    status: str
    approved_at: datetime | None
    updated_at: datetime
    placeholders: list[str] = list(svc.PLACEHOLDERS)


class NotificationOut(BaseModel):
    id: UUID
    channel: str
    recipient: str
    body: str
    status: str
    status_reason: str | None
    related_type: str | None
    related_id: UUID | None
    call_id: UUID | None
    created_at: datetime


def _tpl(ctx: Ctx, tpl_id: UUID) -> NotificationTemplate:
    t = ctx.session.scalar(
        select(NotificationTemplate).where(
            NotificationTemplate.id == tpl_id, NotificationTemplate.tenant_id == ctx.tenant.id
        )
    )
    if not t:
        raise not_found()
    return t


@router.get("/v1/notification-templates", response_model=list[TemplateOut])
def list_templates(ctx: Ctx = Depends(require(Perm.SUPPORT_READ))) -> list[TemplateOut]:
    rows = ctx.session.scalars(select(NotificationTemplate).order_by(NotificationTemplate.key))
    return [TemplateOut.model_validate(t, from_attributes=True) for t in rows]


@router.post("/v1/notification-templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(data: TemplateIn, ctx: Ctx = Depends(require(Perm.NOTIFICATIONS_MANAGE))) -> TemplateOut:
    try:
        svc.check_template(data.body)
    except WorkflowError as e:
        raise bad_request(e.code, e.message) from None
    if ctx.session.scalar(
        select(NotificationTemplate.id).where(
            NotificationTemplate.key == data.key, NotificationTemplate.channel == data.channel
        )
    ):
        raise conflict("duplicate", "A message with that key and channel already exists.")
    t = NotificationTemplate(tenant_id=ctx.tenant.id, **data.model_dump())
    ctx.session.add(t)
    ctx.session.flush()
    ctx.audit("notification_template.created", resource_type="notification_template", resource_id=str(t.id))
    ctx.session.refresh(t)
    return TemplateOut.model_validate(t, from_attributes=True)


@router.patch("/v1/notification-templates/{tpl_id}", response_model=TemplateOut)
def update_template(
    tpl_id: UUID, data: TemplatePatch, ctx: Ctx = Depends(require(Perm.NOTIFICATIONS_MANAGE))
) -> TemplateOut:
    t = _tpl(ctx, tpl_id)
    if data.body is not None and data.body != t.body:
        try:
            svc.check_template(data.body)
        except WorkflowError as e:
            raise bad_request(e.code, e.message) from None
        t.body = data.body
        if t.status == "approved" and data.status is None:
            t.status, t.approved_at, t.approved_by_membership_id = "draft", None, None  # changed text: approve again
    if data.name is not None:
        t.name = data.name
    if data.subject is not None:
        t.subject = data.subject or None
    if data.status and data.status != t.status:
        t.status = data.status
        if data.status == "approved":
            t.approved_at, t.approved_by_membership_id = datetime.now(UTC), ctx.membership.id
    ctx.session.flush()
    ctx.audit(
        "notification_template.updated", resource_type="notification_template", resource_id=str(t.id), status=t.status
    )
    ctx.session.refresh(t)
    return TemplateOut.model_validate(t, from_attributes=True)


@router.get("/v1/notifications", response_model=list[NotificationOut])
def list_notifications(ctx: Ctx = Depends(require(Perm.SUPPORT_READ))) -> list[NotificationOut]:
    rows = ctx.session.scalars(select(Notification).order_by(Notification.created_at.desc()).limit(200))
    return [NotificationOut.model_validate(n, from_attributes=True) for n in rows]


@router.get("/v1/notification-channels")
def channels(ctx: Ctx = Depends(require(Perm.SUPPORT_READ))) -> list[dict]:
    return [
        {
            "channel": c,
            "status": "configured" if p else "awaiting_configuration",
            "note": None if p else f"No {c.upper()} provider account is configured. Messages are kept as held.",
        }
        for c, p in svc.DELIVERY_PROVIDERS.items()
    ]
