# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    reference: Mapped[str] = mapped_column(String)
    subject: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, server_default="")
    priority: Mapped[str] = mapped_column(String, server_default="normal")
    status: Mapped[str] = mapped_column(String, server_default="open")
    requester_name: Mapped[str] = mapped_column(String, server_default="")
    requester_phone: Mapped[str | None] = mapped_column(String)
    requester_email: Mapped[str | None] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    call_id: Mapped[UUID | None]
    assignee_membership_id: Mapped[UUID | None]
    created_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TicketComment(Base):
    __tablename__ = "ticket_comments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID]
    ticket_id: Mapped[UUID]
    body: Mapped[str] = mapped_column(String)
    internal: Mapped[bool] = mapped_column(Boolean, server_default="true")
    author_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    key: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    channel: Mapped[str] = mapped_column(String)
    subject: Mapped[str | None] = mapped_column(String)
    body: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default="draft")
    approved_by_membership_id: Mapped[UUID | None]
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    template_id: Mapped[UUID]
    channel: Mapped[str] = mapped_column(String)
    recipient: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default="queued")
    status_reason: Mapped[str | None] = mapped_column(String)
    related_type: Mapped[str | None] = mapped_column(String)
    related_id: Mapped[UUID | None]
    call_id: Mapped[UUID | None]
    idempotency_key: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
