# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default="active")
    current_version_id: Mapped[UUID | None]
    created_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentVersion(Base):
    """Immutable: the runtime role can insert and read versions, never change them."""

    __tablename__ = "agent_versions"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    agent_id: Mapped[UUID]
    version: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict] = mapped_column(JSONB)
    created_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
