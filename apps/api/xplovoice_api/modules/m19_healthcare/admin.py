# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Super Admin healthcare console (M19 activation, M21 vendor BAAs, M25 customer BAAs and control tests).

Activation needs a platform admin with a two-factor session and a written reason, every gate check passing, and
an admin who is not the person who requested it (also a database check). The gate result is stored with the
profile. The console never reads PHI: no transcripts, PHI access rows or rights requests of an organisation."""

from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...core import audit
from ...core.config import get_settings
from ...core.context import Ctx
from ...core.errors import conflict, forbidden, not_found
from ..m02_tenant.models import Tenant
from ..m03_ai.models import Provider
from ..m15_usage.billing_admin import as_tenant
from ..m17_admin.router import platform_admin
from ..m25_evidence import controls
from . import gate
from .models import Evidence, HealthcareProfile, Incident, VendorRecord

router = APIRouter(prefix="/admin/v1/healthcare", tags=["M17 Super Admin"])


def _log(ctx: Ctx, action: str, rtype: str, rid: str | None, reason: str | None = None, **meta: Any) -> None:
    audit.record(
        ctx.session,
        action=action,
        result="success",
        tenant_id=None,
        actor_user_id=ctx.user.id,
        actor_kind="platform_admin",
        resource_type=rtype,
        resource_id=rid,
        reason=reason,
        ip_hash=ctx.meta.ip_hash,
        correlation_id=ctx.meta.correlation_id,
        metadata=meta,
    )


class ReasonIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class GateCheck(BaseModel):
    key: str
    label: str
    ok: bool
    detail: str


class AdminProfileOut(BaseModel):
    tenant_id: UUID
    tenant_name: str
    country_code: str
    status: str
    entity_type: str
    privacy_contact: str
    synthetic_data_only: bool
    requested_by_user_id: UUID
    requested_at: datetime
    activated_at: datetime | None
    activation_reason: str | None
    suspended_at: datetime | None
    suspended_reason: str | None
    gate: list[GateCheck]
    gate_passed: bool


class EvidenceOut(BaseModel):
    id: UUID
    kind: str
    title: str
    status: str
    valid_from: date
    valid_until: date | None
    reference: str
    details: dict
    created_at: datetime


def _out(ctx: Ctx, p: HealthcareProfile, t: Tenant) -> AdminProfileOut:
    with as_tenant(ctx, t.id):
        checks = gate.evaluate(ctx.session, t, p)
    return AdminProfileOut(
        tenant_id=t.id,
        tenant_name=t.name,
        country_code=t.country_code,
        gate=[GateCheck(**c.__dict__) for c in checks],
        gate_passed=all(c.ok for c in checks),
        **{
            k: getattr(p, k)
            for k in AdminProfileOut.model_fields
            if k not in ("tenant_id", "tenant_name", "country_code", "gate", "gate_passed")
        },
    )


def _load(ctx: Ctx, tenant_id: UUID) -> tuple[HealthcareProfile, Tenant]:
    row = ctx.session.execute(
        select(HealthcareProfile, Tenant)
        .join(Tenant, Tenant.id == HealthcareProfile.tenant_id)
        .where(HealthcareProfile.tenant_id == tenant_id)
    ).first()
    if row is None:
        raise not_found("This organisation has not asked for Healthcare Mode")
    return row[0], row[1]


@router.get("/tenants", response_model=list[AdminProfileOut])
def list_profiles(ctx: Ctx = Depends(platform_admin)) -> list[AdminProfileOut]:
    rows = ctx.session.execute(
        select(HealthcareProfile, Tenant)
        .join(Tenant, Tenant.id == HealthcareProfile.tenant_id)
        .order_by(HealthcareProfile.requested_at.desc())
        .limit(200)
    ).all()
    _log(ctx, "admin.healthcare_listed", "healthcare_profile", None)
    return [_out(ctx, p, t) for p, t in rows]


@router.get("/tenants/{tenant_id}", response_model=AdminProfileOut)
def get_profile(tenant_id: UUID, ctx: Ctx = Depends(platform_admin)) -> AdminProfileOut:
    p, t = _load(ctx, tenant_id)
    return _out(ctx, p, t)


@router.get("/tenants/{tenant_id}/evidence", response_model=list[EvidenceOut])
def tenant_evidence(tenant_id: UUID, ctx: Ctx = Depends(platform_admin)) -> list[EvidenceOut]:
    rows = ctx.session.scalars(
        select(Evidence).where(Evidence.tenant_id == tenant_id).order_by(Evidence.created_at.desc()).limit(100)
    )
    return [EvidenceOut.model_validate(e, from_attributes=True) for e in rows]


class BaaIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    signed_on: date
    valid_until: date | None = None
    reference: str = Field(min_length=3, max_length=300)
    reason: str = Field(min_length=5, max_length=500)


@router.post("/tenants/{tenant_id}/baa", response_model=EvidenceOut, status_code=status.HTTP_201_CREATED)
def record_customer_baa(tenant_id: UUID, data: BaaIn, ctx: Ctx = Depends(platform_admin)) -> EvidenceOut:
    """Records that Xplosys and the organisation signed a business associate agreement (a reference to where the
    signed document is kept, not the document)."""
    _load(ctx, tenant_id)
    e = Evidence(
        tenant_id=tenant_id,
        kind="customer_baa",
        title=data.title,
        valid_from=data.signed_on,
        valid_until=data.valid_until,
        reference=data.reference,
        recorded_by_user_id=ctx.user.id,
        recorded_kind="platform",
    )
    ctx.session.add(e)
    ctx.session.flush()
    ctx.session.refresh(e)
    _log(ctx, "admin.customer_baa_recorded", "tenant", str(tenant_id), data.reason, evidence=str(e.id))
    return EvidenceOut.model_validate(e, from_attributes=True)


@router.post("/tenants/{tenant_id}/activate", response_model=AdminProfileOut)
def activate(tenant_id: UUID, data: ReasonIn, ctx: Ctx = Depends(platform_admin)) -> AdminProfileOut:
    p, t = _load(ctx, tenant_id)
    if p.status not in ("requested", "suspended"):
        raise conflict("not_requested", f"This profile is {p.status}.")
    if p.requested_by_user_id == ctx.user.id:
        raise forbidden("The person who asked for Healthcare Mode can't also activate it")
    with as_tenant(ctx, t.id):
        checks = gate.evaluate(ctx.session, t, p)
    failed = [c.key for c in checks if not c.ok]
    if failed:
        _log(ctx, "admin.healthcare_activation_refused", "tenant", str(t.id), data.reason, failed=failed)
        ctx.session.commit()
        raise conflict("gate_failed", "The activation gate is not passed: " + ", ".join(failed))
    now = datetime.now(UTC)
    p.status, p.activated_by_user_id, p.activated_at, p.activation_reason = "active", ctx.user.id, now, data.reason
    p.gate_snapshot = {"evaluated_at": now.isoformat(), "checks": gate.as_dicts(checks)}
    p.suspended_at = p.suspended_reason = None
    p.updated_at = now
    _log(ctx, "admin.healthcare_activated", "tenant", str(t.id), data.reason)
    with as_tenant(ctx, t.id):
        audit.record(
            ctx.session,
            action="healthcare.activated",
            result="success",
            tenant_id=t.id,
            actor_user_id=ctx.user.id,
            actor_kind="platform_admin",
            resource_type="healthcare_profile",
            resource_id=str(p.id),
            reason=data.reason,
            correlation_id=ctx.meta.correlation_id,
        )
    return _out(ctx, p, t)


@router.post("/tenants/{tenant_id}/suspend", response_model=AdminProfileOut)
def suspend(tenant_id: UUID, data: ReasonIn, ctx: Ctx = Depends(platform_admin)) -> AdminProfileOut:
    """Stops new calls for the organisation. Every PHI protection stays on."""
    p, t = _load(ctx, tenant_id)
    if p.status != "active":
        raise conflict("not_active", "Only an active healthcare organisation can be suspended.")
    now = datetime.now(UTC)
    p.status, p.suspended_at, p.suspended_reason, p.updated_at = "suspended", now, data.reason, now
    _log(ctx, "admin.healthcare_suspended", "tenant", str(t.id), data.reason)
    return _out(ctx, p, t)


# ---------------------------------------------------------------------------------------------------- vendors (M21)
class VendorIn(BaseModel):
    vendor_type: Literal["ai_provider", "telephony", "hosting", "other"]
    vendor_key: str = Field(pattern=r"^[a-z0-9_-]{2,60}$")
    vendor_name: str = Field(min_length=2, max_length=120)
    services: str = Field(default="", max_length=300)
    baa_status: Literal["signed", "terminated"]
    signed_on: date | None = None
    expires_on: date | None = None
    reference: str = Field(min_length=3, max_length=300)
    notes: str = Field(default="", max_length=500)
    reason: str = Field(min_length=5, max_length=500)


class VendorOut(BaseModel):
    id: UUID
    vendor_type: str
    vendor_key: str
    vendor_name: str
    services: str
    baa_status: str
    signed_on: date | None
    expires_on: date | None
    reference: str
    notes: str
    created_at: datetime


@router.get("/vendors", response_model=list[VendorOut])
def list_vendors(ctx: Ctx = Depends(platform_admin)) -> list[VendorOut]:
    rows = ctx.session.scalars(select(VendorRecord).order_by(VendorRecord.created_at.desc()).limit(500))
    return [VendorOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/vendors", response_model=VendorOut, status_code=status.HTTP_201_CREATED)
def record_vendor(data: VendorIn, ctx: Ctx = Depends(platform_admin)) -> VendorOut:
    """Adds a BAA record. For an AI provider, a signed BAA sets the catalog's BAA status (an admin still decides
    to approve it for PHI); a terminated one also withdraws the PHI approval at once."""
    if data.baa_status == "signed" and data.signed_on is None:
        raise conflict("signed_on_required", "Give the date the BAA was signed.")
    provider = None
    if data.vendor_type == "ai_provider":
        provider = ctx.session.scalar(select(Provider).where(Provider.key == data.vendor_key))
        if provider is None:
            raise not_found("No AI provider with this key")
    r = VendorRecord(
        recorded_by=ctx.user.id,
        **data.model_dump(exclude={"reason"}),
    )
    ctx.session.add(r)
    if provider is not None:
        if data.baa_status == "signed":
            provider.baa_status = "signed"
        else:
            provider.phi_eligible, provider.baa_status = False, "none"
    ctx.session.flush()
    ctx.session.refresh(r)
    _log(
        ctx,
        "admin.vendor_baa_recorded",
        "vendor",
        f"{data.vendor_type}:{data.vendor_key}",
        data.reason,
        baa_status=data.baa_status,
    )
    return VendorOut.model_validate(r, from_attributes=True)


# ---------------------------------------------------------------------------------------------------- control tests
@router.get("/control-tests", response_model=list[EvidenceOut])
def control_runs(ctx: Ctx = Depends(platform_admin)) -> list[EvidenceOut]:
    rows = ctx.session.scalars(
        select(Evidence)
        .where(Evidence.tenant_id.is_(None), Evidence.kind == "control_test")
        .order_by(Evidence.created_at.desc())
        .limit(20)
    )
    return [EvidenceOut.model_validate(e, from_attributes=True) for e in rows]


@router.post("/control-tests/run", response_model=EvidenceOut, status_code=status.HTTP_201_CREATED)
def run_controls(data: ReasonIn, ctx: Ctx = Depends(platform_admin)) -> EvidenceOut:
    result = controls.run(ctx.session)
    passed = sum(r["passed"] for r in result["results"])
    e = Evidence(
        tenant_id=None,
        kind="control_test",
        title=f"Security control tests: {passed} of {len(result['results'])} passed",
        reference=f"commit {get_settings().commit_sha}",
        details=result,
        recorded_by_user_id=ctx.user.id,
        recorded_kind="platform",
    )
    ctx.session.add(e)
    ctx.session.flush()
    ctx.session.refresh(e)
    _log(ctx, "admin.control_tests_run", "evidence", str(e.id), data.reason, passed=result["passed"])
    return EvidenceOut.model_validate(e, from_attributes=True)


# ---------------------------------------------------------------------------------------------------- incidents
class AdminIncidentOut(BaseModel):
    id: UUID
    tenant_id: UUID
    tenant_name: str
    title: str
    category: str
    severity: str
    status: str
    phi_involved: str
    affected_individuals: int
    discovered_at: datetime


@router.get("/incidents", response_model=list[AdminIncidentOut])
def incidents(ctx: Ctx = Depends(platform_admin)) -> list[AdminIncidentOut]:
    rows = ctx.session.execute(
        select(Incident, Tenant.name)
        .join(Tenant, Tenant.id == Incident.tenant_id)
        .order_by(Incident.created_at.desc())
        .limit(200)
    ).all()
    _log(ctx, "admin.incidents_listed", "incident", None)
    return [
        AdminIncidentOut(
            tenant_name=name, **{k: getattr(i, k) for k in AdminIncidentOut.model_fields if k != "tenant_name"}
        )
        for i, name in rows
    ]
