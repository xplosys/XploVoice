# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import datetime, time
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Integer, String, Time, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(String)
    purpose: Mapped[str] = mapped_column(String, server_default="")
    agent_id: Mapped[UUID]
    from_number_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(String, server_default="draft")
    timezone: Mapped[str] = mapped_column(String)
    window_start: Mapped[time] = mapped_column(Time)
    window_end: Mapped[time] = mapped_column(Time)
    days: Mapped[list[str]] = mapped_column(ARRAY(String))
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="2")
    retry_minutes: Mapped[int] = mapped_column(Integer, server_default="120")
    max_concurrent: Mapped[int] = mapped_column(Integer, server_default="1")
    calls_per_minute: Mapped[int] = mapped_column(Integer, server_default="2")
    approved_by_membership_id: Mapped[UUID | None]
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CampaignContact(Base):
    __tablename__ = "campaign_contacts"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    campaign_id: Mapped[UUID]
    phone: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String, server_default="")
    timezone: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_outcome: Mapped[str | None] = mapped_column(String)
    last_call_id: Mapped[UUID | None]
    block_reason: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DialAttempt(Base):
    __tablename__ = "dial_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID]
    campaign_id: Mapped[UUID]
    contact_id: Mapped[UUID]
    call_id: Mapped[UUID]
    attempt_no: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(String)
    sip_status: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PolicyDecision(Base):
    __tablename__ = "policy_decisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID]
    campaign_id: Mapped[UUID | None]
    contact_id: Mapped[UUID | None]
    call_id: Mapped[UUID | None]
    phone: Mapped[str] = mapped_column(String)
    purpose: Mapped[str] = mapped_column(String)
    decision: Mapped[str] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(String)
    checks: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
