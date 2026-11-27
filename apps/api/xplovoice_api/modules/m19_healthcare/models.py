# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base


def _ts() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class HealthcareProfile(Base):
    __tablename__ = "healthcare_tenant_profiles"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(String, server_default="requested")
    jurisdiction: Mapped[str] = mapped_column(String)
    entity_type: Mapped[str] = mapped_column(String)
    privacy_contact: Mapped[str] = mapped_column(String)
    synthetic_data_only: Mapped[bool] = mapped_column(Boolean, server_default="true")
    requested_by_user_id: Mapped[UUID]
    requested_at: Mapped[datetime] = _ts()
    activated_by_user_id: Mapped[UUID | None]
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activation_reason: Mapped[str | None] = mapped_column(String)
    gate_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_reason: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[datetime] = _ts()


class HealthcarePolicy(Base):
    __tablename__ = "healthcare_policies"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    version: Mapped[int] = mapped_column(Integer)
    recording_mode: Mapped[str] = mapped_column(String, server_default="off")
    privacy_notice: Mapped[str] = mapped_column(String, server_default="")
    allow_outbound_campaigns: Mapped[bool] = mapped_column(Boolean, server_default="false")
    change_note: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default="draft")
    created_by_membership_id: Mapped[UUID]
    created_at: Mapped[datetime] = _ts()
    approved_by_membership_id: Mapped[UUID | None]
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PhiClassification(Base):
    __tablename__ = "phi_data_classifications"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    resource_type: Mapped[str] = mapped_column(String)
    classification: Mapped[str] = mapped_column(String)
    locked: Mapped[bool] = mapped_column(Boolean, server_default="false")
    note: Mapped[str] = mapped_column(String, server_default="")
    updated_by_membership_id: Mapped[UUID | None]
    updated_at: Mapped[datetime] = _ts()


class VendorRecord(Base):
    __tablename__ = "vendor_compliance_records"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    vendor_type: Mapped[str] = mapped_column(String)
    vendor_key: Mapped[str] = mapped_column(String)
    vendor_name: Mapped[str] = mapped_column(String)
    services: Mapped[str] = mapped_column(String, server_default="")
    baa_status: Mapped[str] = mapped_column(String)
    signed_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)
    reference: Mapped[str] = mapped_column(String)
    notes: Mapped[str] = mapped_column(String, server_default="")
    recorded_by: Mapped[UUID | None]
    created_at: Mapped[datetime] = _ts()


class PhiAccess(Base):
    __tablename__ = "phi_access_audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID]
    actor_user_id: Mapped[UUID | None]
    actor_kind: Mapped[str] = mapped_column(String, server_default="user")
    action: Mapped[str] = mapped_column(String)
    resource_type: Mapped[str] = mapped_column(String)
    resource_id: Mapped[str | None] = mapped_column(String)
    purpose: Mapped[str] = mapped_column(String, server_default="")
    result: Mapped[str] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(String)
    correlation_id: Mapped[str | None] = mapped_column(String)
    ip_hash: Mapped[str | None] = mapped_column(String)
    occurred_at: Mapped[datetime] = _ts()


class Incident(Base):
    __tablename__ = "security_incidents"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(String, server_default="")
    category: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default="open")
    phi_involved: Mapped[str] = mapped_column(String, server_default="unknown")
    affected_individuals: Mapped[int] = mapped_column(Integer, server_default="0")
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reported_by_membership_id: Mapped[UUID]
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by_membership_id: Mapped[UUID | None]
    close_note: Mapped[str | None] = mapped_column(String)


class BreachAssessment(Base):
    __tablename__ = "breach_assessments"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    incident_id: Mapped[UUID]
    nature_and_extent: Mapped[str] = mapped_column(String)
    unauthorized_recipient: Mapped[str] = mapped_column(String)
    acquired_or_viewed: Mapped[str] = mapped_column(String)
    mitigation: Mapped[str] = mapped_column(String)
    risk: Mapped[str] = mapped_column(String)
    exception: Mapped[str] = mapped_column(String, server_default="none")
    determination: Mapped[str] = mapped_column(String)
    assessed_by_membership_id: Mapped[UUID]
    assessed_at: Mapped[datetime] = _ts()


class BreachNotification(Base):
    __tablename__ = "breach_notifications"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    incident_id: Mapped[UUID]
    audience: Mapped[str] = mapped_column(String)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    method: Mapped[str | None] = mapped_column(String)
    note: Mapped[str | None] = mapped_column(String)
    recorded_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = _ts()


class RetentionPolicy(Base):
    __tablename__ = "healthcare_retention_policies"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    resource_type: Mapped[str] = mapped_column(String)
    retain_days: Mapped[int] = mapped_column(Integer)
    updated_by_membership_id: Mapped[UUID | None]
    updated_at: Mapped[datetime] = _ts()


class LegalHold(Base):
    __tablename__ = "legal_holds"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    scope: Mapped[str] = mapped_column(String)
    call_id: Mapped[UUID | None]
    phone: Mapped[str | None] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    placed_by_membership_id: Mapped[UUID]
    placed_at: Mapped[datetime] = _ts()
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by_membership_id: Mapped[UUID | None]
    release_reason: Mapped[str | None] = mapped_column(String)


class RightsRequest(Base):
    __tablename__ = "retention_requests"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String)
    subject_phone: Mapped[str] = mapped_column(String)
    subject_reference: Mapped[str] = mapped_column(String, server_default="")
    details: Mapped[str] = mapped_column(String, server_default="")
    status: Mapped[str] = mapped_column(String, server_default="received")
    received_at: Mapped[datetime] = _ts()
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_membership_id: Mapped[UUID]
    decided_by_membership_id: Mapped[UUID | None]
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(String)
    completed_by_membership_id: Mapped[UUID | None]
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[dict | None] = mapped_column(JSONB)


class RetentionRun(Base):
    __tablename__ = "retention_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    started_by_membership_id: Mapped[UUID | None]
    ran_at: Mapped[datetime] = _ts()
    calls_purged: Mapped[int] = mapped_column(Integer, server_default="0")
    skipped_on_hold: Mapped[int] = mapped_column(Integer, server_default="0")
    details: Mapped[dict] = mapped_column(JSONB, server_default="{}")


class Evidence(Base):
    __tablename__ = "compliance_evidence"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID | None]
    kind: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default="valid")
    valid_from: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    valid_until: Mapped[date | None] = mapped_column(Date)
    reference: Mapped[str] = mapped_column(String, server_default="")
    details: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    recorded_by_user_id: Mapped[UUID | None]
    recorded_kind: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = _ts()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String)


class Risk(Base):
    __tablename__ = "compliance_risks"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, server_default="")
    likelihood: Mapped[int] = mapped_column(Integer)
    impact: Mapped[int] = mapped_column(Integer)
    mitigation: Mapped[str] = mapped_column(String, server_default="")
    status: Mapped[str] = mapped_column(String, server_default="open")
    review_by: Mapped[date | None] = mapped_column(Date)
    created_by_membership_id: Mapped[UUID]
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()
