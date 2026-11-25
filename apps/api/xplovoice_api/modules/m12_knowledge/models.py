# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, server_default="")
    status: Mapped[str] = mapped_column(String, server_default="active")
    created_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KbDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    kb_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    filename: Mapped[str | None] = mapped_column(String)
    mime: Mapped[str | None] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default="scanning")
    scan_engine: Mapped[str | None] = mapped_column(String)
    scan_result: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(String)
    chunk_count: Mapped[int] = mapped_column(Integer, server_default="0")
    char_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KbChunk(Base):
    __tablename__ = "kb_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID]
    kb_id: Mapped[UUID]
    document_id: Mapped[UUID]
    seq: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(String)
