# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base


class CallQueue(Base):
    __tablename__ = "call_queues"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(String)
    max_waiting: Mapped[int] = mapped_column(Integer, server_default="5")
    max_wait_seconds: Mapped[int] = mapped_column(Integer, server_default="60")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InboundRoute(Base):
    __tablename__ = "inbound_routes"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    phone_number_id: Mapped[UUID]
    agent_id: Mapped[UUID]
    queue_id: Mapped[UUID | None]
    fallback_action: Mapped[str] = mapped_column(String, server_default="message")
    fallback_message: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default="active")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
