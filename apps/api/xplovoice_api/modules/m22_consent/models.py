# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    phone: Mapped[str] = mapped_column(String)
    purpose: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    basis: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    evidence: Mapped[str] = mapped_column(String, server_default="")
    call_id: Mapped[UUID | None]
    captured_by_membership_id: Mapped[UUID | None]
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String)


class SuppressionEntry(Base):
    __tablename__ = "suppression_entries"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    phone: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    note: Mapped[str] = mapped_column(String, server_default="")
    call_id: Mapped[UUID | None]
    created_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by_membership_id: Mapped[UUID | None]
    removed_reason: Mapped[str | None] = mapped_column(String)
