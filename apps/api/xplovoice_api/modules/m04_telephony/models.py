# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base


class TelephonyProvider(Base):
    __tablename__ = "telephony_providers"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    capabilities: Mapped[dict] = mapped_column(JSONB)
    note: Mapped[str | None] = mapped_column(String)


class SipTrunk(Base):
    __tablename__ = "sip_trunks"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(String)
    provider_key: Mapped[str] = mapped_column(String)
    direction: Mapped[str] = mapped_column(String, server_default="both")
    address: Mapped[str | None] = mapped_column(String)
    transport: Mapped[str] = mapped_column(String, server_default="udp")
    auth_username: Mapped[str | None] = mapped_column(String)
    auth_secret_ciphertext: Mapped[str | None] = mapped_column(String)
    allowed_addresses: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    capabilities: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    status: Mapped[str] = mapped_column(String, server_default="active")
    sync_status: Mapped[str] = mapped_column(String, server_default="pending")
    sync_error: Mapped[str | None] = mapped_column(String)
    livekit_inbound_trunk_id: Mapped[str | None] = mapped_column(String)
    livekit_outbound_trunk_id: Mapped[str | None] = mapped_column(String)
    livekit_dispatch_rule_id: Mapped[str | None] = mapped_column(String)
    created_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PhoneNumber(Base):
    __tablename__ = "phone_numbers"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    e164: Mapped[str] = mapped_column(String)
    country_code: Mapped[str] = mapped_column(String)
    trunk_id: Mapped[UUID]
    label: Mapped[str] = mapped_column(String, server_default="")
    inbound: Mapped[bool] = mapped_column(Boolean, server_default="true")
    outbound: Mapped[bool] = mapped_column(Boolean, server_default="true")
    status: Mapped[str] = mapped_column(String, server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DestinationPolicy(Base):
    __tablename__ = "destination_policies"

    tenant_id: Mapped[UUID] = mapped_column(primary_key=True)
    telephony_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    allowed_countries: Mapped[list[str]] = mapped_column(ARRAY(String))
    block_premium: Mapped[bool] = mapped_column(Boolean, server_default="true")
    max_concurrent_outbound: Mapped[int] = mapped_column(Integer, server_default="2")
    daily_outbound_minutes: Mapped[int] = mapped_column(Integer, server_default="120")
    updated_by_membership_id: Mapped[UUID | None]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CallProviderRef(Base):
    __tablename__ = "call_provider_refs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID]
    call_id: Mapped[UUID]
    provider_key: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    ref: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CallProviderEvent(Base):
    __tablename__ = "call_provider_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID]
    call_id: Mapped[UUID]
    provider_key: Mapped[str] = mapped_column(String)
    event_id: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    state: Mapped[str | None] = mapped_column(String)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    applied: Mapped[bool] = mapped_column(Boolean)
    data: Mapped[dict] = mapped_column(JSONB, server_default="{}")


class CallStateTransition(Base):
    __tablename__ = "call_state_transitions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID]
    call_id: Mapped[UUID]
    from_state: Mapped[str] = mapped_column(String)
    to_state: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(String)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TelephonyUsage(Base):
    __tablename__ = "telephony_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID]
    call_id: Mapped[UUID]
    provider_key: Mapped[str] = mapped_column(String)
    trunk_id: Mapped[UUID | None]
    direction: Mapped[str] = mapped_column(String)
    country_code: Mapped[str | None] = mapped_column(String)
    connected_seconds: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    pulse_seconds: Mapped[int] = mapped_column(Integer)
    billed_seconds: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
