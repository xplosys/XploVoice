# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base


class BookingCalendar(Base):
    __tablename__ = "booking_calendars"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(String)
    timezone: Mapped[str] = mapped_column(String)
    slot_minutes: Mapped[int] = mapped_column(Integer, server_default="30")
    weekly: Mapped[dict] = mapped_column(JSONB)
    min_notice_minutes: Mapped[int] = mapped_column(Integer, server_default="60")
    horizon_days: Mapped[int] = mapped_column(Integer, server_default="30")
    status: Mapped[str] = mapped_column(String, server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    calendar_id: Mapped[UUID | None]
    day: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    calendar_id: Mapped[UUID]
    reference: Mapped[str] = mapped_column(String)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, server_default="booked")
    customer_name: Mapped[str] = mapped_column(String)
    customer_phone: Mapped[str | None] = mapped_column(String)
    customer_email: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str] = mapped_column(String, server_default="")
    source: Mapped[str] = mapped_column(String)
    call_id: Mapped[UUID | None]
    cancelled_reason: Mapped[str | None] = mapped_column(String)
    created_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    company: Mapped[str] = mapped_column(String, server_default="")
    interest: Mapped[str] = mapped_column(String, server_default="")
    budget: Mapped[str] = mapped_column(String, server_default="")
    timeline: Mapped[str] = mapped_column(String, server_default="")
    score: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, server_default="new")
    source: Mapped[str] = mapped_column(String)
    call_id: Mapped[UUID | None]
    owner_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LeadActivity(Base):
    __tablename__ = "lead_activities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID]
    lead_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(String, server_default="")
    call_id: Mapped[UUID | None]
    created_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    lead_id: Mapped[UUID | None]
    ticket_id: Mapped[UUID | None]
    appointment_id: Mapped[UUID | None]
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    channel: Mapped[str] = mapped_column(String, server_default="call")
    note: Mapped[str] = mapped_column(String, server_default="")
    status: Mapped[str] = mapped_column(String, server_default="open")
    source: Mapped[str] = mapped_column(String)
    call_id: Mapped[UUID | None]
    assignee_membership_id: Mapped[UUID | None]
    created_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
