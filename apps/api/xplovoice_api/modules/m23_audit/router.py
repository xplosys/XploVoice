# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""PHI access log, security incidents and breach assessment (M23).

The breach assessment follows the four-factor risk assessment. A breach determination creates the notifications
it needs with their target dates: individuals within 60 days of discovery, HHS within 60 days when 500 or more
people are affected (otherwise within 60 days after the end of the calendar year), and the media when 500 or more
are affected; a business associate notifies the covered entity instead. XploVoice tracks these dates and who
recorded each notice; it sends nothing and gives no legal advice: confirm deadlines with counsel."""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from ...core.context import Ctx, require
from ...core.errors import bad_request, conflict, not_found
from ...core.permissions import Perm
from ..m19_healthcare.mode import profile
from ..m19_healthcare.models import BreachAssessment, BreachNotification, Incident, PhiAccess
from ..m20_phi.classify import redact

router = APIRouter(tags=["audit and breach"])


# ---------------------------------------------------------------------------------------------------- PHI access log
class PhiAccessOut(BaseModel):
    id: int
    actor_user_id: UUID | None
    actor_kind: str
    action: str
    resource_type: str
    resource_id: str | None
    purpose: str
    result: str
    reason: str | None
    correlation_id: str | None
    occurred_at: datetime


@router.get("/v1/audit/phi-access", response_model=list[PhiAccessOut])
def phi_access(
    resource_id: str | None = Query(default=None, max_length=100),
    actor_user_id: UUID | None = None,
    result: Literal["allowed", "denied"] | None = None,
    since: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    ctx: Ctx = Depends(require(Perm.PHI_AUDIT_READ)),
) -> list[PhiAccessOut]:
    q = select(PhiAccess).where(PhiAccess.tenant_id == ctx.tenant.id)
    if resource_id:
        q = q.where(PhiAccess.resource_id == resource_id)
    if actor_user_id:
        q = q.where(PhiAccess.actor_user_id == actor_user_id)
    if result:
        q = q.where(PhiAccess.result == result)
    if since:
        q = q.where(PhiAccess.occurred_at >= since)
    rows = ctx.session.scalars(q.order_by(PhiAccess.id.desc()).limit(limit))
    ctx.audit("phi_access_log.viewed", resource_type="phi_access_log")
    return [PhiAccessOut.model_validate(r, from_attributes=True) for r in rows]


# ---------------------------------------------------------------------------------------------------- incidents
Category = Literal[
    "unauthorized_access",
    "misdirected_communication",
    "lost_device",
    "vendor_incident",
    "system_vulnerability",
    "other",
]


class IncidentIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    summary: str = Field(default="", max_length=4000)
    category: Category
    severity: Literal["low", "medium", "high", "critical"]
    phi_involved: Literal["unknown", "yes", "no"] = "unknown"
    affected_individuals: int = Field(default=0, ge=0, le=100_000_000)
    discovered_at: datetime


class IncidentUpdate(BaseModel):
    severity: Literal["low", "medium", "high", "critical"] | None = None
    phi_involved: Literal["unknown", "yes", "no"] | None = None
    affected_individuals: int | None = Field(default=None, ge=0, le=100_000_000)


class AssessmentIn(BaseModel):
    nature_and_extent: str = Field(min_length=3, max_length=2000)
    unauthorized_recipient: str = Field(min_length=3, max_length=2000)
    acquired_or_viewed: str = Field(min_length=3, max_length=2000)
    mitigation: str = Field(min_length=3, max_length=2000)
    risk: Literal["low", "not_low"]
    exception: Literal[
        "none", "unintentional_workforce_access", "inadvertent_internal_disclosure", "unable_to_retain"
    ] = "none"


class AssessmentOut(BaseModel):
    id: UUID
    nature_and_extent: str
    unauthorized_recipient: str
    acquired_or_viewed: str
    mitigation: str
    risk: str
    exception: str
    determination: str
    assessed_by_membership_id: UUID
    assessed_at: datetime


class NotificationOut(BaseModel):
    id: UUID
    audience: str
    due_at: datetime
    sent_at: datetime | None
    method: str | None
    note: str | None


class SentIn(BaseModel):
    sent_at: datetime | None = None
    method: str = Field(min_length=2, max_length=100)
    note: str = Field(default="", max_length=500)


class CloseIn(BaseModel):
    note: str = Field(min_length=5, max_length=1000)


class IncidentOut(BaseModel):
    id: UUID
    title: str
    summary: str
    category: str
    severity: str
    status: str
    phi_involved: str
    affected_individuals: int
    discovered_at: datetime
    created_at: datetime
    closed_at: datetime | None
    close_note: str | None
    determination: str | None = None
    next_due_at: datetime | None = None


class IncidentDetail(IncidentOut):
    assessments: list[AssessmentOut]
    notifications: list[NotificationOut]


def _clean(text_: str) -> str:
    """Incident records describe what happened, never whose data: identifiers are redacted on save."""
    return redact(text_)[0]


def _get(ctx: Ctx, incident_id: UUID) -> Incident:
    i = ctx.session.scalar(select(Incident).where(Incident.id == incident_id, Incident.tenant_id == ctx.tenant.id))
    if i is None:
        raise not_found()
    return i


def _summary(ctx: Ctx, i: Incident) -> IncidentOut:
    a = ctx.session.scalar(
        select(BreachAssessment)
        .where(BreachAssessment.incident_id == i.id)
        .order_by(BreachAssessment.assessed_at.desc())
    )
    due = ctx.session.scalar(
        select(BreachNotification.due_at)
        .where(BreachNotification.incident_id == i.id, BreachNotification.sent_at.is_(None))
        .order_by(BreachNotification.due_at)
        .limit(1)
    )
    return IncidentOut(
        determination=a.determination if a else None,
        next_due_at=due,
        **{k: getattr(i, k) for k in IncidentOut.model_fields if k not in ("determination", "next_due_at")},
    )


def _detail(ctx: Ctx, i: Incident) -> IncidentDetail:
    return IncidentDetail(
        **_summary(ctx, i).model_dump(),
        assessments=[
            AssessmentOut.model_validate(a, from_attributes=True)
            for a in ctx.session.scalars(
                select(BreachAssessment)
                .where(BreachAssessment.incident_id == i.id)
                .order_by(BreachAssessment.assessed_at.desc())
            )
        ],
        notifications=[
            NotificationOut.model_validate(n, from_attributes=True)
            for n in ctx.session.scalars(
                select(BreachNotification)
                .where(BreachNotification.incident_id == i.id)
                .order_by(BreachNotification.due_at)
            )
        ],
    )


@router.get("/v1/incidents", response_model=list[IncidentOut])
def list_incidents(ctx: Ctx = Depends(require(Perm.INCIDENTS_MANAGE))) -> list[IncidentOut]:
    rows = ctx.session.scalars(
        select(Incident).where(Incident.tenant_id == ctx.tenant.id).order_by(Incident.created_at.desc()).limit(200)
    )
    return [_summary(ctx, i) for i in rows]


@router.post("/v1/incidents", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
def report_incident(data: IncidentIn, ctx: Ctx = Depends(require(Perm.INCIDENTS_REPORT))) -> IncidentOut:
    if data.discovered_at > datetime.now(UTC) + timedelta(minutes=5):
        raise bad_request("discovered_in_future", "The discovery time can't be in the future.")
    i = Incident(
        tenant_id=ctx.tenant.id,
        title=_clean(data.title),
        summary=_clean(data.summary),
        category=data.category,
        severity=data.severity,
        phi_involved=data.phi_involved,
        affected_individuals=data.affected_individuals,
        discovered_at=data.discovered_at,
        reported_by_membership_id=ctx.membership.id,
    )
    ctx.session.add(i)
    ctx.session.flush()
    ctx.session.refresh(i)
    ctx.audit("incident.reported", resource_type="incident", resource_id=str(i.id), severity=data.severity)
    return _summary(ctx, i)


@router.get("/v1/incidents/{incident_id}", response_model=IncidentDetail)
def get_incident(incident_id: UUID, ctx: Ctx = Depends(require(Perm.INCIDENTS_MANAGE))) -> IncidentDetail:
    return _detail(ctx, _get(ctx, incident_id))


@router.patch("/v1/incidents/{incident_id}", response_model=IncidentDetail)
def update_incident(
    incident_id: UUID, data: IncidentUpdate, ctx: Ctx = Depends(require(Perm.INCIDENTS_MANAGE))
) -> IncidentDetail:
    i = _get(ctx, incident_id)
    if i.status == "closed":
        raise conflict("closed", "This incident is closed.")
    changes = data.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(i, k, v)
    i.updated_at = datetime.now(UTC)
    ctx.audit("incident.updated", resource_type="incident", resource_id=str(i.id), fields=sorted(changes))
    return _detail(ctx, i)


def notification_plan(i: Incident, business_associate: bool) -> list[tuple[str, datetime]]:
    sixty = i.discovered_at + timedelta(days=60)
    if business_associate:
        return [("covered_entity", sixty)]
    plan = [("individuals", sixty)]
    if i.affected_individuals >= 500:
        plan += [("hhs", sixty), ("media", sixty)]
    else:
        year_end = datetime(i.discovered_at.year + 1, 1, 1, tzinfo=UTC)
        plan.append(("hhs", year_end + timedelta(days=60)))
    return plan


@router.post("/v1/incidents/{incident_id}/assessment", response_model=IncidentDetail)
def assess(incident_id: UUID, data: AssessmentIn, ctx: Ctx = Depends(require(Perm.INCIDENTS_MANAGE))) -> IncidentDetail:
    """Records the four-factor assessment. A low probability of compromise, or one of the three exceptions, means
    no breach; anything else is a breach and the notifications are scheduled."""
    i = _get(ctx, incident_id)
    if i.status == "closed":
        raise conflict("closed", "This incident is closed.")
    determination = "not_a_breach" if data.risk == "low" or data.exception != "none" else "breach"
    ctx.session.add(
        BreachAssessment(
            tenant_id=ctx.tenant.id,
            incident_id=i.id,
            nature_and_extent=_clean(data.nature_and_extent),
            unauthorized_recipient=_clean(data.unauthorized_recipient),
            acquired_or_viewed=_clean(data.acquired_or_viewed),
            mitigation=_clean(data.mitigation),
            risk=data.risk,
            exception=data.exception,
            determination=determination,
            assessed_by_membership_id=ctx.membership.id,
        )
    )
    if determination == "breach":
        prof = profile(ctx.session)
        ba = bool(prof and prof.entity_type == "business_associate")
        for audience, due in notification_plan(i, ba):
            ctx.session.execute(
                insert(BreachNotification)
                .values(tenant_id=ctx.tenant.id, incident_id=i.id, audience=audience, due_at=due)
                .on_conflict_do_nothing(index_elements=["incident_id", "audience"])
            )
        i.status, i.phi_involved = "notifying", "yes"
    else:
        i.status = "assessing"
    i.updated_at = datetime.now(UTC)
    ctx.session.flush()
    ctx.audit("incident.assessed", resource_type="incident", resource_id=str(i.id), determination=determination)
    return _detail(ctx, i)


@router.post("/v1/incidents/{incident_id}/notifications/{notification_id}/sent", response_model=IncidentDetail)
def notification_sent(
    incident_id: UUID, notification_id: UUID, data: SentIn, ctx: Ctx = Depends(require(Perm.INCIDENTS_MANAGE))
) -> IncidentDetail:
    i = _get(ctx, incident_id)
    n = ctx.session.scalar(
        select(BreachNotification).where(
            BreachNotification.id == notification_id, BreachNotification.incident_id == i.id
        )
    )
    if n is None:
        raise not_found()
    if n.sent_at is not None:
        raise conflict("already_recorded", "This notice is already recorded as sent.")
    n.sent_at, n.method, n.note = data.sent_at or datetime.now(UTC), data.method, _clean(data.note)
    n.recorded_by_membership_id = ctx.membership.id
    ctx.audit("incident.notice_recorded", resource_type="incident", resource_id=str(i.id), audience=n.audience)
    return _detail(ctx, i)


@router.post("/v1/incidents/{incident_id}/close", response_model=IncidentDetail)
def close_incident(
    incident_id: UUID, data: CloseIn, ctx: Ctx = Depends(require(Perm.INCIDENTS_MANAGE))
) -> IncidentDetail:
    i = _get(ctx, incident_id)
    if i.status == "closed":
        raise conflict("closed", "This incident is already closed.")
    if ctx.session.scalar(select(BreachAssessment.id).where(BreachAssessment.incident_id == i.id).limit(1)) is None:
        raise conflict("not_assessed", "Record the risk assessment before closing the incident.")
    pending = ctx.session.scalar(
        select(BreachNotification.id)
        .where(BreachNotification.incident_id == i.id, BreachNotification.sent_at.is_(None))
        .limit(1)
    )
    if pending is not None:
        raise conflict("notices_pending", "Record every required notice as sent before closing.")
    now = datetime.now(UTC)
    i.status, i.closed_at, i.closed_by_membership_id, i.close_note, i.updated_at = (
        "closed",
        now,
        ctx.membership.id,
        _clean(data.note),
        now,
    )
    ctx.audit("incident.closed", resource_type="incident", resource_id=str(i.id))
    return _detail(ctx, i)
