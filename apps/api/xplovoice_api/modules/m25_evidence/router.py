# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Compliance evidence, risk register and report (M25). Evidence is an inventory of references (where the signed
document or result lives), not a file store. The report gathers what an assessor would ask for first; it states
facts recorded in XploVoice and is not a certification of anything."""

from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from ...core.context import Ctx, require
from ...core.errors import conflict, not_found
from ...core.permissions import Perm
from ..m19_healthcare import gate
from ..m19_healthcare.models import (
    Evidence,
    HealthcareProfile,
    Incident,
    PhiAccess,
    RetentionPolicy,
    RightsRequest,
    Risk,
)
from ..m19_healthcare.router import CheckOut

router = APIRouter(tags=["compliance"])


class EvidenceOut(BaseModel):
    id: UUID
    tenant_id: UUID | None
    kind: str
    title: str
    status: str
    valid_from: date
    valid_until: date | None
    reference: str
    details: dict
    recorded_kind: str
    created_at: datetime
    revoked_at: datetime | None
    revoked_reason: str | None


class EvidenceIn(BaseModel):
    kind: Literal["risk_assessment", "training", "policy_document", "penetration_test", "other"]
    title: str = Field(min_length=3, max_length=200)
    valid_from: date | None = None
    valid_until: date | None = None
    reference: str = Field(default="", max_length=300)


class RevokeIn(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


def _evidence(ctx: Ctx) -> list[Evidence]:
    return list(
        ctx.session.scalars(
            select(Evidence)
            .where(or_(Evidence.tenant_id == ctx.tenant.id, Evidence.tenant_id.is_(None)))
            .order_by(Evidence.created_at.desc())
            .limit(200)
        )
    )


@router.get("/v1/compliance/evidence", response_model=list[EvidenceOut])
def list_evidence(ctx: Ctx = Depends(require(Perm.HEALTHCARE_READ))) -> list[EvidenceOut]:
    """The organisation's evidence and the platform's control-test runs."""
    return [EvidenceOut.model_validate(e, from_attributes=True) for e in _evidence(ctx)]


@router.post("/v1/compliance/evidence", response_model=EvidenceOut, status_code=status.HTTP_201_CREATED)
def add_evidence(data: EvidenceIn, ctx: Ctx = Depends(require(Perm.EVIDENCE_MANAGE))) -> EvidenceOut:
    e = Evidence(
        tenant_id=ctx.tenant.id,
        kind=data.kind,
        title=data.title,
        valid_from=data.valid_from or datetime.now(UTC).date(),
        valid_until=data.valid_until,
        reference=data.reference,
        recorded_by_user_id=ctx.user.id,
        recorded_kind="tenant",
    )
    ctx.session.add(e)
    ctx.session.flush()
    ctx.session.refresh(e)
    ctx.audit("evidence.recorded", resource_type="evidence", resource_id=str(e.id), kind=data.kind)
    return EvidenceOut.model_validate(e, from_attributes=True)


@router.post("/v1/compliance/evidence/{evidence_id}/revoke", response_model=EvidenceOut)
def revoke_evidence(
    evidence_id: UUID, data: RevokeIn, ctx: Ctx = Depends(require(Perm.EVIDENCE_MANAGE))
) -> EvidenceOut:
    e = ctx.session.scalar(
        select(Evidence).where(
            Evidence.id == evidence_id, Evidence.tenant_id == ctx.tenant.id, Evidence.recorded_kind == "tenant"
        )
    )
    if e is None:
        raise not_found()
    if e.status == "revoked":
        raise conflict("already_revoked", "This evidence is already revoked.")
    e.status, e.revoked_at, e.revoked_reason = "revoked", datetime.now(UTC), data.reason
    ctx.audit("evidence.revoked", resource_type="evidence", resource_id=str(e.id), reason=data.reason[:200])
    return EvidenceOut.model_validate(e, from_attributes=True)


# ---------------------------------------------------------------------------------------------------- risks
class RiskIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=2000)
    likelihood: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    mitigation: str = Field(default="", max_length=2000)
    review_by: date | None = None


class RiskUpdate(BaseModel):
    status: Literal["open", "mitigating", "accepted", "closed"] | None = None
    likelihood: int | None = Field(default=None, ge=1, le=5)
    impact: int | None = Field(default=None, ge=1, le=5)
    mitigation: str | None = Field(default=None, max_length=2000)
    review_by: date | None = None


class RiskOut(BaseModel):
    id: UUID
    title: str
    description: str
    likelihood: int
    impact: int
    score: int
    mitigation: str
    status: str
    review_by: date | None
    created_at: datetime
    updated_at: datetime


def _risk(r: Risk) -> RiskOut:
    return RiskOut(score=r.likelihood * r.impact, **{k: getattr(r, k) for k in RiskOut.model_fields if k != "score"})


@router.get("/v1/compliance/risks", response_model=list[RiskOut])
def list_risks(ctx: Ctx = Depends(require(Perm.HEALTHCARE_READ))) -> list[RiskOut]:
    rows = ctx.session.scalars(select(Risk).where(Risk.tenant_id == ctx.tenant.id).order_by(Risk.created_at.desc()))
    return sorted((_risk(r) for r in rows), key=lambda r: (r.status == "closed", -r.score))


@router.post("/v1/compliance/risks", response_model=RiskOut, status_code=status.HTTP_201_CREATED)
def add_risk(data: RiskIn, ctx: Ctx = Depends(require(Perm.EVIDENCE_MANAGE))) -> RiskOut:
    r = Risk(tenant_id=ctx.tenant.id, created_by_membership_id=ctx.membership.id, **data.model_dump())
    ctx.session.add(r)
    ctx.session.flush()
    ctx.session.refresh(r)
    ctx.audit("risk.recorded", resource_type="risk", resource_id=str(r.id), score=r.likelihood * r.impact)
    return _risk(r)


@router.patch("/v1/compliance/risks/{risk_id}", response_model=RiskOut)
def update_risk(risk_id: UUID, data: RiskUpdate, ctx: Ctx = Depends(require(Perm.EVIDENCE_MANAGE))) -> RiskOut:
    r = ctx.session.scalar(select(Risk).where(Risk.id == risk_id, Risk.tenant_id == ctx.tenant.id))
    if r is None:
        raise not_found()
    changes = data.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(r, k, v)
    r.updated_at = datetime.now(UTC)
    ctx.audit("risk.updated", resource_type="risk", resource_id=str(r.id), fields=sorted(changes))
    return _risk(r)


# ---------------------------------------------------------------------------------------------------- report
class ReportOut(BaseModel):
    organisation: str
    generated_at: datetime
    mode: str
    gate: list[CheckOut]
    evidence: list[EvidenceOut]
    open_risks: list[RiskOut]
    open_incidents: int
    retention: dict[str, int]
    phi_accesses_30_days: int
    phi_denials_30_days: int
    rights_requests_open: int
    rights_requests_overdue: int
    statement: str


@router.get("/v1/compliance/report", response_model=ReportOut)
def report(ctx: Ctx = Depends(require(Perm.HEALTHCARE_READ))) -> ReportOut:
    s = ctx.session
    now = datetime.now(UTC)
    since = now - timedelta(days=30)
    prof = s.scalar(select(HealthcareProfile).where(HealthcareProfile.tenant_id == ctx.tenant.id))

    def count(q) -> int:  # type: ignore[no-untyped-def]
        return s.scalar(q) or 0

    ctx.audit("compliance.report_viewed", resource_type="compliance_report")
    return ReportOut(
        organisation=ctx.tenant.name,
        generated_at=now,
        mode=prof.status if prof else "off",
        gate=[CheckOut(**c.__dict__) for c in gate.evaluate(s, ctx.tenant, prof)],
        evidence=[EvidenceOut.model_validate(e, from_attributes=True) for e in _evidence(ctx) if e.status == "valid"],
        open_risks=[r for r in list_risks(ctx) if r.status != "closed"],
        open_incidents=count(
            select(func.count())
            .select_from(Incident)
            .where(Incident.tenant_id == ctx.tenant.id, Incident.status != "closed")
        ),
        retention={
            r.resource_type: r.retain_days
            for r in s.scalars(select(RetentionPolicy).where(RetentionPolicy.tenant_id == ctx.tenant.id))
        },
        phi_accesses_30_days=count(
            select(func.count())
            .select_from(PhiAccess)
            .where(PhiAccess.tenant_id == ctx.tenant.id, PhiAccess.occurred_at >= since)
        ),
        phi_denials_30_days=count(
            select(func.count())
            .select_from(PhiAccess)
            .where(PhiAccess.tenant_id == ctx.tenant.id, PhiAccess.occurred_at >= since, PhiAccess.result == "denied")
        ),
        rights_requests_open=count(
            select(func.count())
            .select_from(RightsRequest)
            .where(RightsRequest.tenant_id == ctx.tenant.id, RightsRequest.status.in_(("received", "approved")))
        ),
        rights_requests_overdue=count(
            select(func.count())
            .select_from(RightsRequest)
            .where(
                RightsRequest.tenant_id == ctx.tenant.id,
                RightsRequest.status.in_(("received", "approved")),
                RightsRequest.due_at < now,
            )
        ),
        statement="This report lists what is recorded in XploVoice. It is not a certification or a statement of "
        "HIPAA compliance, which depends on your agreements, configuration and an independent assessment.",
    )
