# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Healthcare compliance API for an organisation (M19, M20, M21 eligibility).

An organisation asks for Healthcare Mode, writes and approves its healthcare policy (two different people), keeps
its PHI inventory, and sees the activation gate. Turning the mode on is a platform-admin step (admin.py)."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from ...core.config import get_settings
from ...core.context import Ctx, require
from ...core.errors import bad_request, conflict, forbidden, not_found
from ...core.permissions import Perm
from ..m20_phi.classify import DEFAULT_INVENTORY
from . import gate
from .mode import PHI_STATUSES, policy_in_force
from .models import HealthcarePolicy, HealthcareProfile, PhiClassification

router = APIRouter(tags=["healthcare"])


class CheckOut(BaseModel):
    key: str
    label: str
    ok: bool
    detail: str


class ProfileOut(BaseModel):
    status: str
    jurisdiction: str
    entity_type: str
    privacy_contact: str
    synthetic_data_only: bool
    requested_at: datetime
    activated_at: datetime | None
    suspended_at: datetime | None
    suspended_reason: str | None


class PolicyOut(BaseModel):
    id: UUID
    version: int
    recording_mode: str
    privacy_notice: str
    allow_outbound_campaigns: bool
    change_note: str
    status: str
    created_by_membership_id: UUID
    created_at: datetime
    approved_by_membership_id: UUID | None
    approved_at: datetime | None


class ClassificationOut(BaseModel):
    resource_type: str
    classification: str
    locked: bool
    note: str
    updated_at: datetime


class HealthcareOut(BaseModel):
    mode: str  # off | requested | active | suspended | withdrawn
    phi_protections: bool
    platform_enabled: bool
    environment: str
    profile: ProfileOut | None
    policy_version_in_force: int | None
    gate: list[CheckOut]
    gate_passed: bool
    policies: list[PolicyOut]
    classifications: list[ClassificationOut]


def _profile(ctx: Ctx) -> HealthcareProfile | None:
    return ctx.session.scalar(select(HealthcareProfile).where(HealthcareProfile.tenant_id == ctx.tenant.id))


def overview(ctx: Ctx) -> HealthcareOut:
    p = _profile(ctx)
    checks = gate.evaluate(ctx.session, ctx.tenant, p)
    pols = ctx.session.scalars(
        select(HealthcarePolicy)
        .where(HealthcarePolicy.tenant_id == ctx.tenant.id)
        .order_by(HealthcarePolicy.version.desc())
        .limit(20)
    )
    cls = ctx.session.scalars(
        select(PhiClassification)
        .where(PhiClassification.tenant_id == ctx.tenant.id)
        .order_by(PhiClassification.resource_type)
    )
    return HealthcareOut(
        mode=p.status if p else "off",
        phi_protections=bool(p and p.status in PHI_STATUSES),
        platform_enabled=get_settings().healthcare_enabled,
        environment=get_settings().environment,
        profile=ProfileOut.model_validate(p, from_attributes=True) if p else None,
        policy_version_in_force=policy_in_force(ctx.session).version,
        gate=[CheckOut(**c.__dict__) for c in checks],
        gate_passed=all(c.ok for c in checks),
        policies=[PolicyOut.model_validate(x, from_attributes=True) for x in pols],
        classifications=[ClassificationOut.model_validate(x, from_attributes=True) for x in cls],
    )


@router.get("/v1/healthcare", response_model=HealthcareOut)
def get_healthcare(ctx: Ctx = Depends(require(Perm.HEALTHCARE_READ))) -> HealthcareOut:
    return overview(ctx)


class RequestIn(BaseModel):
    entity_type: Literal["covered_entity", "business_associate"]
    privacy_contact: str = Field(min_length=3, max_length=200)
    synthetic_data_only: bool


def seed_inventory(ctx: Ctx) -> None:
    for rtype, cls, locked, note in DEFAULT_INVENTORY:
        ctx.session.execute(
            insert(PhiClassification)
            .values(tenant_id=ctx.tenant.id, resource_type=rtype, classification=cls, locked=locked, note=note)
            .on_conflict_do_nothing(index_elements=["tenant_id", "resource_type"])
        )


@router.post("/v1/healthcare/request", response_model=HealthcareOut, status_code=status.HTTP_201_CREATED)
def request_mode(data: RequestIn, ctx: Ctx = Depends(require(Perm.HEALTHCARE_MANAGE))) -> HealthcareOut:
    """Asks Xplosys to turn Healthcare Mode on. Needs a two-factor session. Outside production the requester must
    confirm that only synthetic data will be used."""
    if not ctx.mfa:
        raise forbidden("Sign in with two-factor authentication to ask for Healthcare Mode")
    if ctx.tenant.country_code != "US":
        raise bad_request("jurisdiction", "Healthcare Mode is offered to US organisations only.")
    if get_settings().environment != "production" and not data.synthetic_data_only:
        raise bad_request(
            "synthetic_data_only", "Outside production, Healthcare Mode may only be used with synthetic data."
        )
    p = _profile(ctx)
    now = datetime.now(UTC)
    if p is not None and p.status in ("requested", *PHI_STATUSES):
        raise conflict("already_requested", "Healthcare Mode has already been requested for this organisation.")
    if p is None:
        p = HealthcareProfile(tenant_id=ctx.tenant.id, jurisdiction="US", requested_by_user_id=ctx.user.id)
        ctx.session.add(p)
    p.status, p.entity_type, p.privacy_contact = "requested", data.entity_type, data.privacy_contact
    p.synthetic_data_only, p.requested_by_user_id, p.requested_at, p.updated_at = (
        data.synthetic_data_only,
        ctx.user.id,
        now,
        now,
    )
    ctx.session.flush()
    seed_inventory(ctx)
    ctx.audit(
        "healthcare.requested", resource_type="healthcare_profile", resource_id=str(p.id), entity=data.entity_type
    )
    return overview(ctx)


@router.post("/v1/healthcare/withdraw", response_model=HealthcareOut)
def withdraw(ctx: Ctx = Depends(require(Perm.HEALTHCARE_MANAGE))) -> HealthcareOut:
    """Withdraws a request that is not active yet. Once active, Healthcare Mode is left only with Xplosys, because
    the PHI already held must stay protected."""
    p = _profile(ctx)
    if p is None or p.status != "requested":
        raise conflict("not_requested", "Only a pending request can be withdrawn.")
    p.status, p.updated_at = "withdrawn", datetime.now(UTC)
    ctx.audit("healthcare.withdrawn", resource_type="healthcare_profile", resource_id=str(p.id))
    return overview(ctx)


# ---------------------------------------------------------------------------------------------------- policies
class PolicyIn(BaseModel):
    recording_mode: Literal["off", "consent_required"] = "off"
    privacy_notice: str = Field(default="", max_length=400)
    allow_outbound_campaigns: bool = False
    change_note: str = Field(min_length=3, max_length=500)


@router.post("/v1/healthcare/policies", response_model=PolicyOut, status_code=status.HTTP_201_CREATED)
def new_policy(data: PolicyIn, ctx: Ctx = Depends(require(Perm.HEALTHCARE_MANAGE))) -> PolicyOut:
    if _profile(ctx) is None:
        raise conflict("not_requested", "Ask for Healthcare Mode first.")
    n = (
        ctx.session.scalar(
            select(func.max(HealthcarePolicy.version)).where(HealthcarePolicy.tenant_id == ctx.tenant.id)
        )
        or 0
    )
    for d in ctx.session.scalars(
        select(HealthcarePolicy).where(HealthcarePolicy.tenant_id == ctx.tenant.id, HealthcarePolicy.status == "draft")
    ):
        d.status = "superseded"  # one draft at a time
    p = HealthcarePolicy(
        tenant_id=ctx.tenant.id,
        version=n + 1,
        recording_mode=data.recording_mode,
        privacy_notice=data.privacy_notice.strip(),
        allow_outbound_campaigns=data.allow_outbound_campaigns,
        change_note=data.change_note,
        created_by_membership_id=ctx.membership.id,
    )
    ctx.session.add(p)
    ctx.session.flush()
    ctx.audit("healthcare.policy_drafted", resource_type="healthcare_policy", resource_id=str(p.id), version=p.version)
    ctx.session.refresh(p)
    return PolicyOut.model_validate(p, from_attributes=True)


@router.post("/v1/healthcare/policies/{policy_id}/approve", response_model=PolicyOut)
def approve_policy(policy_id: UUID, ctx: Ctx = Depends(require(Perm.HEALTHCARE_MANAGE))) -> PolicyOut:
    p = ctx.session.scalar(
        select(HealthcarePolicy).where(HealthcarePolicy.id == policy_id, HealthcarePolicy.tenant_id == ctx.tenant.id)
    )
    if p is None:
        raise not_found()
    if p.status != "draft":
        raise conflict("not_draft", "Only a draft can be approved.")
    if p.created_by_membership_id == ctx.membership.id:
        raise forbidden("Someone other than the author must approve a policy version")
    now = datetime.now(UTC)
    for old in ctx.session.scalars(
        select(HealthcarePolicy).where(
            HealthcarePolicy.tenant_id == ctx.tenant.id, HealthcarePolicy.status == "approved"
        )
    ):
        old.status = "superseded"
    p.status, p.approved_by_membership_id, p.approved_at = "approved", ctx.membership.id, now
    ctx.audit("healthcare.policy_approved", resource_type="healthcare_policy", resource_id=str(p.id), version=p.version)
    return PolicyOut.model_validate(p, from_attributes=True)


# ---------------------------------------------------------------------------------------------------- PHI inventory
class ClassificationIn(BaseModel):
    classification: Literal["phi", "review", "not_phi"]
    note: str = Field(default="", max_length=300)


@router.put("/v1/healthcare/classifications/{resource_type}", response_model=ClassificationOut)
def set_classification(
    resource_type: str, data: ClassificationIn, ctx: Ctx = Depends(require(Perm.HEALTHCARE_MANAGE))
) -> ClassificationOut:
    row = ctx.session.scalar(
        select(PhiClassification).where(
            PhiClassification.tenant_id == ctx.tenant.id, PhiClassification.resource_type == resource_type
        )
    )
    if row is None:
        raise not_found()
    if row.locked and data.classification != "phi":
        raise conflict("locked", "This kind of record always holds PHI.")
    row.classification, row.note = data.classification, data.note or row.note
    row.updated_by_membership_id, row.updated_at = ctx.membership.id, datetime.now(UTC)
    ctx.audit(
        "healthcare.classification_changed",
        resource_type="phi_classification",
        resource_id=resource_type,
        classification=data.classification,
    )
    return ClassificationOut.model_validate(row, from_attributes=True)
