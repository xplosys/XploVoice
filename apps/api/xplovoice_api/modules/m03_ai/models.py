# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ARRAY, Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base


class Provider(Base):
    __tablename__ = "ai_providers"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    key: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    adapter: Mapped[str] = mapped_column(String)
    hosting: Mapped[str] = mapped_column(String)
    kinds: Mapped[list[str]] = mapped_column(ARRAY(String))
    base_url: Mapped[str | None] = mapped_column(String)
    regions: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    managed_available: Mapped[bool] = mapped_column(Boolean, server_default="false")
    customer_keys_allowed: Mapped[bool] = mapped_column(Boolean, server_default="true")
    phi_eligible: Mapped[bool] = mapped_column(Boolean, server_default="false")
    baa_status: Mapped[str] = mapped_column(String, server_default="none")
    rate_limit_rpm: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, server_default="active")
    notes: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Model(Base):
    __tablename__ = "ai_models"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    provider_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String)
    model_key: Mapped[str] = mapped_column(String)
    display_name: Mapped[str] = mapped_column(String)
    languages: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    streaming: Mapped[bool] = mapped_column(Boolean, server_default="false")
    function_calling: Mapped[bool] = mapped_column(Boolean, server_default="false")
    context_window: Mapped[int | None] = mapped_column(Integer)
    voices: Mapped[list] = mapped_column(JSONB, server_default="[]")
    regions: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    status: Mapped[str] = mapped_column(String, server_default="active")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RateCard(Base):
    __tablename__ = "ai_rate_cards"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    model_id: Mapped[UUID]
    unit: Mapped[str] = mapped_column(String)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(24, 12))
    currency: Mapped[str] = mapped_column(String)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str] = mapped_column(String)
    created_by: Mapped[UUID | None]


class PlatformRoute(Base):
    __tablename__ = "platform_ai_routes"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    kind: Mapped[str] = mapped_column(String)
    priority: Mapped[int] = mapped_column(Integer)
    model_id: Mapped[UUID]
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")


class Credential(Base):
    __tablename__ = "ai_credentials"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    provider_id: Mapped[UUID]
    label: Mapped[str] = mapped_column(String)
    secret_enc: Mapped[str] = mapped_column(String)
    secret_hint: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default="active")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String)
    created_by_membership_id: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TenantRoute(Base):
    __tablename__ = "tenant_ai_routes"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String)
    priority: Mapped[int] = mapped_column(Integer)
    model_id: Mapped[UUID]
    credential_id: Mapped[UUID | None]
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
