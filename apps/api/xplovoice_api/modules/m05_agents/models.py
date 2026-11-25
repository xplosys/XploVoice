# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, server_default="")
    status: Mapped[str] = mapped_column(String, server_default="draft")
    template_key: Mapped[str | None] = mapped_column(String)
    current_version_id: Mapped[UUID | None]  # latest saved version: what test calls use
    published_version_id: Mapped[UUID | None]  # what live traffic uses (telephony, Phase 6)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    content_hash: Mapped[str] = mapped_column(String)
    note: Mapped[str | None] = mapped_column(String)
    created_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentPublication(Base):
    """Append-only history of what was live and who changed it."""

    __tablename__ = "agent_publications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID]
    agent_id: Mapped[UUID]
    version_id: Mapped[UUID | None]
    action: Mapped[str] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(String)
    created_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentTemplate(Base):
    __tablename__ = "agent_templates"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    config: Mapped[dict] = mapped_column(JSONB)
    sort: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
