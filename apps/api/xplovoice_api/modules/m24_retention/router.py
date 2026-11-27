# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Retention and patient rights (M24, LLD v1.3 section 10).

Retention: how long call content (transcripts, call event and tool payloads, the other party's number) is kept
after a call ends. A retention run purges what is older, except calls under a legal hold. Purging goes through the
database function purge_call_content, which checks the hold again, so no code path can skip it.

Rights requests: access (an export of the person's calls), amendment (a statement appended to their calls,
never an edit), deletion (purge, refused while a hold applies) and restriction (recorded). A request is decided
by someone other than the person who logged it. Target dates follow common practice (30 days; 60 for amendment)
and are for tracking only."""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError

from ...core.context import Ctx, require
from ...core.errors import bad_request, conflict, forbidden, not_found
from ...core.permissions import Perm, has
from ..m04_telephony.service import TelephonyError, e164
from ..m08_calls.models import Call, CallEvent, TranscriptSegment
from ..m19_healthcare.mode import profile
from ..m19_healthcare.models import LegalHold, RetentionPolicy, RetentionRun, RightsRequest
from ..m23_audit.service import log

router = APIRouter(tags=["retention and rights"])
DUE_DAYS = {"access": 30, "amendment": 60, "deletion": 30, "restriction": 30}


class LegalHoldError(Exception):
    pass


def purge(ctx: Ctx, call_id: UUID) -> bool:
    """Purges one call's content. Raises LegalHoldError when a hold applies."""
    try:
        with ctx.session.begin_nested():
            done = bool(ctx.session.scalar(text("select purge_call_content(:c)"), {"c": call_id}))
    except DBAPIError as e:
        if "legal_hold" in str(e.orig):
            raise LegalHoldError from None
        raise
    if done:
        log(ctx, "purge", "call_content", str(call_id), purpose="retention")
    return done


def _phone(ctx: Ctx, value: str) -> str:
    try:
        return e164(value, ctx.tenant.country_code)[0]
    except TelephonyError as e:
        raise bad_request(e.code, e.message) from None


def _need_profile(ctx: Ctx) -> None:
    if profile(ctx.session) is None:
        raise conflict("healthcare_off", "Retention and rights requests are part of Healthcare Mode. Ask for it first.")


# ---------------------------------------------------------------------------------------------------- schemas
class PolicyOut(BaseModel):
    resource_type: str
    retain_days: int
    updated_at: datetime


class HoldOut(BaseModel):
    id: UUID
    scope: str
    call_id: UUID | None
    phone: str | None
    reason: str
    placed_at: datetime
    released_at: datetime | None
    release_reason: str | None


class RequestOut(BaseModel):
    id: UUID
    kind: str
    subject_phone: str
    subject_reference: str
    details: str
    status: str
    received_at: datetime
    due_at: datetime
    created_by_membership_id: UUID
    decided_by_membership_id: UUID | None
    decided_at: datetime | None
    decision_reason: str | None
    completed_at: datetime | None
    outcome: dict | None


class RunOut(BaseModel):
    id: UUID
    ran_at: datetime
    calls_purged: int
    skipped_on_hold: int


class RetentionOut(BaseModel):
    policies: list[PolicyOut]
    holds: list[HoldOut]
    requests: list[RequestOut]
    runs: list[RunOut]


def _request_out(ctx: Ctx, r: RightsRequest) -> RequestOut:
    out = RequestOut.model_validate(r, from_attributes=True)
    if not has(ctx.membership.role, Perm.PHI_READ):
        out.subject_phone = r.subject_phone[:2] + "•" * max(0, len(r.subject_phone) - 6) + r.subject_phone[-4:]
    return out


@router.get("/v1/retention", response_model=RetentionOut)
def overview(ctx: Ctx = Depends(require(Perm.RETENTION_MANAGE))) -> RetentionOut:
    s, t = ctx.session, ctx.tenant.id
    return RetentionOut(
        policies=[
            PolicyOut.model_validate(p, from_attributes=True)
            for p in s.scalars(select(RetentionPolicy).where(RetentionPolicy.tenant_id == t))
        ],
        holds=[
            HoldOut.model_validate(h, from_attributes=True)
            for h in s.scalars(select(LegalHold).where(LegalHold.tenant_id == t).order_by(LegalHold.placed_at.desc()))
        ],
        requests=[
            _request_out(ctx, r)
            for r in s.scalars(
                select(RightsRequest).where(RightsRequest.tenant_id == t).order_by(RightsRequest.received_at.desc())
            )
        ],
        runs=[
            RunOut.model_validate(r, from_attributes=True)
            for r in s.scalars(
                select(RetentionRun).where(RetentionRun.tenant_id == t).order_by(RetentionRun.ran_at.desc()).limit(20)
            )
        ],
    )


class PolicyIn(BaseModel):
    retain_days: int = Field(ge=1, le=36500)


@router.put("/v1/retention/policies/{resource_type}", response_model=PolicyOut)
def set_policy(
    resource_type: Literal["call_content", "call_recording"],
    data: PolicyIn,
    ctx: Ctx = Depends(require(Perm.RETENTION_MANAGE)),
) -> PolicyOut:
    _need_profile(ctx)
    now = datetime.now(UTC)
    ctx.session.execute(
        insert(RetentionPolicy)
        .values(
            tenant_id=ctx.tenant.id,
            resource_type=resource_type,
            retain_days=data.retain_days,
            updated_by_membership_id=ctx.membership.id,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "resource_type"],
            set_={"retain_days": data.retain_days, "updated_by_membership_id": ctx.membership.id, "updated_at": now},
        )
    )
    row = ctx.session.scalar(
        select(RetentionPolicy).where(
            RetentionPolicy.tenant_id == ctx.tenant.id, RetentionPolicy.resource_type == resource_type
        )
    )
    assert row is not None
    ctx.session.refresh(row)
    ctx.audit(
        "retention.policy_set", resource_type="retention_policy", resource_id=resource_type, days=data.retain_days
    )
    return PolicyOut.model_validate(row, from_attributes=True)


# ---------------------------------------------------------------------------------------------------- legal holds
class HoldIn(BaseModel):
    scope: Literal["all", "call", "phone"]
    call_id: UUID | None = None
    phone: str | None = Field(default=None, max_length=30)
    reason: str = Field(min_length=5, max_length=500)


class ReleaseIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


@router.post("/v1/retention/holds", response_model=HoldOut, status_code=status.HTTP_201_CREATED)
def place_hold(data: HoldIn, ctx: Ctx = Depends(require(Perm.RETENTION_MANAGE))) -> HoldOut:
    _need_profile(ctx)
    call_id = data.call_id if data.scope == "call" else None
    phone = _phone(ctx, data.phone) if data.scope == "phone" and data.phone else None
    if data.scope == "call" and (
        call_id is None
        or ctx.session.scalar(select(Call.id).where(Call.id == call_id, Call.tenant_id == ctx.tenant.id)) is None
    ):
        raise bad_request("call_required", "Choose a call of your organisation.")
    if data.scope == "phone" and phone is None:
        raise bad_request("phone_required", "Enter the phone number to hold.")
    h = LegalHold(
        tenant_id=ctx.tenant.id,
        scope=data.scope,
        call_id=call_id,
        phone=phone,
        reason=data.reason,
        placed_by_membership_id=ctx.membership.id,
    )
    ctx.session.add(h)
    ctx.session.flush()
    ctx.session.refresh(h)
    ctx.audit("retention.hold_placed", resource_type="legal_hold", resource_id=str(h.id), scope=data.scope)
    return HoldOut.model_validate(h, from_attributes=True)


@router.post("/v1/retention/holds/{hold_id}/release", response_model=HoldOut)
def release_hold(hold_id: UUID, data: ReleaseIn, ctx: Ctx = Depends(require(Perm.RETENTION_MANAGE))) -> HoldOut:
    h = ctx.session.scalar(select(LegalHold).where(LegalHold.id == hold_id, LegalHold.tenant_id == ctx.tenant.id))
    if h is None:
        raise not_found()
    if h.released_at is not None:
        raise conflict("already_released", "This hold was already released.")
    h.released_at, h.released_by_membership_id, h.release_reason = datetime.now(UTC), ctx.membership.id, data.reason
    ctx.audit("retention.hold_released", resource_type="legal_hold", resource_id=str(h.id))
    return HoldOut.model_validate(h, from_attributes=True)


# ---------------------------------------------------------------------------------------------------- retention run
@router.post("/v1/retention/run", response_model=RunOut)
def run_retention(ctx: Ctx = Depends(require(Perm.RETENTION_MANAGE))) -> RunOut:
    _need_profile(ctx)
    pol = ctx.session.scalar(
        select(RetentionPolicy).where(
            RetentionPolicy.tenant_id == ctx.tenant.id, RetentionPolicy.resource_type == "call_content"
        )
    )
    if pol is None:
        raise conflict("no_policy", "Set how long call content is kept first.")
    cutoff = datetime.now(UTC) - timedelta(days=pol.retain_days)
    due = ctx.session.scalars(
        select(Call.id)
        .where(Call.tenant_id == ctx.tenant.id, Call.ended_at < cutoff, Call.content_purged_at.is_(None))
        .order_by(Call.ended_at)
        .limit(5000)
    ).all()
    purged = held = 0
    for cid in due:
        try:
            purged += purge(ctx, cid)
        except LegalHoldError:
            held += 1
    run = RetentionRun(
        tenant_id=ctx.tenant.id,
        started_by_membership_id=ctx.membership.id,
        calls_purged=purged,
        skipped_on_hold=held,
        details={"retain_days": pol.retain_days, "cutoff": cutoff.isoformat()},
    )
    ctx.session.add(run)
    ctx.session.flush()
    ctx.session.refresh(run)
    ctx.audit("retention.run", resource_type="retention_run", resource_id=str(run.id), purged=purged, held=held)
    return RunOut.model_validate(run, from_attributes=True)


# ---------------------------------------------------------------------------------------------------- rights requests
class RightsIn(BaseModel):
    kind: Literal["access", "amendment", "deletion", "restriction"]
    subject_phone: str = Field(min_length=4, max_length=30)
    subject_reference: str = Field(default="", max_length=100)
    details: str = Field(default="", max_length=2000)


class DecideIn(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(min_length=5, max_length=500)


class CompleteIn(BaseModel):
    note: str = Field(default="", max_length=1000)


def _get(ctx: Ctx, request_id: UUID) -> RightsRequest:
    r = ctx.session.scalar(
        select(RightsRequest).where(RightsRequest.id == request_id, RightsRequest.tenant_id == ctx.tenant.id)
    )
    if r is None:
        raise not_found()
    return r


def _subject_calls(ctx: Ctx, phone: str) -> list[Call]:
    return list(
        ctx.session.scalars(
            select(Call)
            .where(
                Call.tenant_id == ctx.tenant.id,
                or_(
                    (Call.direction == "inbound") & (Call.from_number == phone),
                    (Call.direction == "outbound") & (Call.to_number == phone),
                ),
            )
            .order_by(Call.created_at)
        )
    )


@router.post("/v1/retention/requests", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
def log_request(data: RightsIn, ctx: Ctx = Depends(require(Perm.RETENTION_MANAGE))) -> RequestOut:
    _need_profile(ctx)
    now = datetime.now(UTC)
    r = RightsRequest(
        tenant_id=ctx.tenant.id,
        kind=data.kind,
        subject_phone=_phone(ctx, data.subject_phone),
        subject_reference=data.subject_reference,
        details=data.details,
        received_at=now,
        due_at=now + timedelta(days=DUE_DAYS[data.kind]),
        created_by_membership_id=ctx.membership.id,
    )
    ctx.session.add(r)
    ctx.session.flush()
    ctx.session.refresh(r)
    ctx.audit("rights.request_logged", resource_type="rights_request", resource_id=str(r.id), kind=data.kind)
    return _request_out(ctx, r)


@router.post("/v1/retention/requests/{request_id}/decide", response_model=RequestOut)
def decide(request_id: UUID, data: DecideIn, ctx: Ctx = Depends(require(Perm.RETENTION_MANAGE))) -> RequestOut:
    r = _get(ctx, request_id)
    if r.status != "received":
        raise conflict("already_decided", "This request was already decided.")
    if r.created_by_membership_id == ctx.membership.id:
        raise forbidden("Someone other than the person who logged the request must decide it")
    r.status = "approved" if data.decision == "approve" else "rejected"
    r.decided_by_membership_id, r.decided_at, r.decision_reason = ctx.membership.id, datetime.now(UTC), data.reason
    ctx.audit("rights.request_decided", resource_type="rights_request", resource_id=str(r.id), decision=r.status)
    return _request_out(ctx, r)


@router.post("/v1/retention/requests/{request_id}/complete", response_model=RequestOut)
def complete(request_id: UUID, data: CompleteIn, ctx: Ctx = Depends(require(Perm.RETENTION_MANAGE))) -> RequestOut:
    r = _get(ctx, request_id)
    if r.status != "approved":
        raise conflict("not_approved", "Only an approved request can be completed.")
    calls = _subject_calls(ctx, r.subject_phone)
    outcome: dict = {"calls": len(calls), "note": data.note}
    if r.kind == "deletion":
        purged = 0
        try:
            for c in calls:
                purged += purge(ctx, c.id)
        except LegalHoldError:
            raise conflict("legal_hold", "A legal hold covers this person's records. Release it first.") from None
        outcome["purged"] = purged
    elif r.kind == "amendment":
        if len(data.note.strip()) < 5:
            raise bad_request("note_required", "Write the statement to append to the person's records.")
        for c in calls:
            ctx.session.add(
                CallEvent(
                    tenant_id=ctx.tenant.id,
                    call_id=c.id,
                    event_key=f"amendment:{r.id}",
                    type="record.amended",
                    data={"request_id": str(r.id), "statement": data.note[:1000]},
                )
            )
            log(ctx, "amend", "call_content", str(c.id), purpose="rights request")
    r.status, r.completed_at, r.completed_by_membership_id, r.outcome = (
        "completed",
        datetime.now(UTC),
        ctx.membership.id,
        outcome,
    )
    ctx.audit("rights.request_completed", resource_type="rights_request", resource_id=str(r.id), kind=r.kind)
    return _request_out(ctx, r)


@router.get("/v1/retention/requests/{request_id}/export")
def export(request_id: UUID, ctx: Ctx = Depends(require(Perm.RETENTION_MANAGE))) -> dict:
    """The person's calls and transcripts, for an approved access request. Needs phi:read and is logged."""
    r = _get(ctx, request_id)
    if r.kind != "access" or r.status not in ("approved", "completed"):
        raise conflict("not_exportable", "Only an approved access request can be exported.")
    if not has(ctx.membership.role, Perm.PHI_READ):
        log(ctx, "export", "rights_request", str(r.id), allowed=False, reason="no phi:read")
        ctx.session.commit()
        raise forbidden()
    out = []
    for c in _subject_calls(ctx, r.subject_phone):
        segs = ctx.session.scalars(
            select(TranscriptSegment).where(TranscriptSegment.call_id == c.id).order_by(TranscriptSegment.seq)
        )
        out.append(
            {
                "call_id": str(c.id),
                "started_at": c.created_at.isoformat(),
                "ended_at": c.ended_at.isoformat() if c.ended_at else None,
                "direction": c.direction,
                "content_purged": c.content_purged_at is not None,
                "transcript": [{"speaker": x.speaker, "text": x.text} for x in segs],
            }
        )
    log(ctx, "export", "rights_request", str(r.id), purpose="access request")
    ctx.audit("rights.export", resource_type="rights_request", resource_id=str(r.id), calls=len(out))
    return {
        "request_id": str(r.id),
        "subject_phone": r.subject_phone,
        "generated_at": datetime.now(UTC).isoformat(),
        "calls": out,
    }
