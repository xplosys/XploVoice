# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    agent_id: Mapped[UUID]
    agent_version_id: Mapped[UUID]
    channel: Mapped[str] = mapped_column(String)
    direction: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default="created")
    end_reason: Mapped[str | None] = mapped_column(String)
    room_name: Mapped[str] = mapped_column(String)
    correlation_id: Mapped[str] = mapped_column(String)
    language: Mapped[str | None] = mapped_column(String)
    created_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    recoveries: Mapped[int] = mapped_column(Integer, server_default="0")
    providers_used: Mapped[dict] = mapped_column(JSONB, server_default="{}")  # kind -> provider, model, version
    options: Mapped[dict] = mapped_column(JSONB, server_default="{}")  # test-call options, e.g. simulate hours
    # Phase 6: the 15-state lifecycle (addendum E) and the telephone legs of a call
    state: Mapped[str] = mapped_column(String, server_default="initiated")
    state_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    from_number: Mapped[str | None] = mapped_column(String)
    to_number: Mapped[str | None] = mapped_column(String)
    trunk_id: Mapped[UUID | None]
    phone_number_id: Mapped[UUID | None]
    campaign_id: Mapped[UUID | None]
    queue_id: Mapped[UUID | None]
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # Phase 8 retention


class CallEvent(Base):
    __tablename__ = "call_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID]
    call_id: Mapped[UUID]
    event_key: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID]
    call_id: Mapped[UUID]
    seq: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(String)
    language: Mapped[str | None] = mapped_column(String)
    start_ms: Mapped[int | None] = mapped_column(Integer)
    end_ms: Mapped[int | None] = mapped_column(Integer)
    interrupted: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
