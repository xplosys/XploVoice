# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Consent and do-not-call API (M22-core). Records are never deleted. Taking a number off the do-not-call list
needs approve rights, keeps the entry, and says who removed it and why."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...core.context import Ctx, require
from ...core.errors import bad_request, conflict, not_found
from ...core.permissions import Perm
from ..m04_telephony.service import TelephonyError, e164
from . import service as svc
from .models import ConsentRecord, SuppressionEntry

router = APIRouter(tags=["consent"])
Basis = Literal["express_written", "express_verbal", "existing_relationship", "on_call", "other"]
Purpose = Literal["outbound_calls", "recording"]


def phone_for(ctx: Ctx, value: str) -> str:
    try:
        return e164(value, ctx.tenant.country_code)[0]
    except TelephonyError as e:
        raise bad_request(e.code, e.message) from None


# ---------------------------------------------------------------------------------------------------- consent
class ConsentIn(BaseModel):
    phone: str = Field(min_length=4, max_length=30)
    purpose: Purpose = "outbound_calls"
    status: Literal["granted", "declined"] = "granted"
    basis: Basis
    evidence: str = Field(default="", max_length=1000)


class RevokeIn(BaseModel):
    phone: str = Field(min_length=4, max_length=30)
    purpose: Purpose = "outbound_calls"
    reason: str = Field(min_length=1, max_length=200)


class ConsentOut(BaseModel):
    id: UUID
    phone: str
    purpose: str
    status: str
    basis: str
    source: str
    evidence: str
    call_id: UUID | None
    captured_at: datetime
    revoked_at: datetime | None
    revoked_reason: str | None


@router.get("/v1/consent", response_model=list[ConsentOut])
def list_consent(
    phone: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    ctx: Ctx = Depends(require(Perm.CONSENT_READ)),
) -> list[ConsentOut]:
    q = select(ConsentRecord)
    if phone:
        q = q.where(ConsentRecord.phone == phone_for(ctx, phone))
    rows = ctx.session.scalars(q.order_by(ConsentRecord.captured_at.desc()).limit(limit))
    return [ConsentOut.model_validate(c, from_attributes=True) for c in rows]


@router.post("/v1/consent", response_model=ConsentOut, status_code=status.HTTP_201_CREATED)
def add_consent(data: ConsentIn, ctx: Ctx = Depends(require(Perm.CONSENT_MANAGE))) -> ConsentOut:
    phone = phone_for(ctx, data.phone)
    if data.status == "granted" and data.purpose == "outbound_calls" and svc.is_suppressed(ctx.session, phone):
        raise conflict("on_do_not_call_list", "This number is on your do-not-call list. Remove it first.")
    c = svc.record_consent(
        ctx.session,
        tenant_id=ctx.tenant.id,
        phone=phone,
        purpose=data.purpose,
        status=data.status,
        basis=data.basis,
        source="manual",
        evidence=data.evidence,
        membership_id=ctx.membership.id,
    )
    ctx.audit(
        "consent.recorded",
        resource_type="consent",
        resource_id=str(c.id),
        purpose=data.purpose,
        status=data.status,
        basis=data.basis,
    )
    ctx.session.refresh(c)
    return ConsentOut.model_validate(c, from_attributes=True)


@router.post("/v1/consent/revoke")
def revoke_consent(data: RevokeIn, ctx: Ctx = Depends(require(Perm.CONSENT_MANAGE))) -> dict:
    phone = phone_for(ctx, data.phone)
    n = svc.revoke(ctx.session, phone, data.purpose, data.reason)
    ctx.audit("consent.revoked", resource_type="consent", resource_id=phone[-4:], purpose=data.purpose, records=n)
    return {"revoked": n}


# ---------------------------------------------------------------------------------------------------- do not call
class SuppressIn(BaseModel):
    phone: str = Field(min_length=4, max_length=30)
    reason: Literal["opt_out", "do_not_call_registry", "complaint", "manual"] = "manual"
    note: str = Field(default="", max_length=500)


class UnsuppressIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


class SuppressionOut(BaseModel):
    id: UUID
    phone: str
    reason: str
    source: str
    note: str
    call_id: UUID | None
    created_at: datetime
    removed_at: datetime | None
    removed_reason: str | None


@router.get("/v1/suppression", response_model=list[SuppressionOut])
def list_suppression(
    include_removed: bool = False,
    phone: str | None = None,
    ctx: Ctx = Depends(require(Perm.CONSENT_READ)),
) -> list[SuppressionOut]:
    q = select(SuppressionEntry)
    if not include_removed:
        q = q.where(SuppressionEntry.removed_at.is_(None))
    if phone:
        q = q.where(SuppressionEntry.phone == phone_for(ctx, phone))
    rows = ctx.session.scalars(q.order_by(SuppressionEntry.created_at.desc()).limit(1000))
    return [SuppressionOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/v1/suppression", response_model=SuppressionOut, status_code=status.HTTP_201_CREATED)
def add_suppression(data: SuppressIn, ctx: Ctx = Depends(require(Perm.CONSENT_MANAGE))) -> SuppressionOut:
    """Adds a number to the do-not-call list. Its open campaign contacts stop at once, on every campaign."""
    from ..m07_campaigns.models import CampaignContact

    phone = phone_for(ctx, data.phone)
    added = svc.suppress(
        ctx.session,
        tenant_id=ctx.tenant.id,
        phone=phone,
        reason=data.reason,
        source="manual",
        note=data.note,
        membership_id=ctx.membership.id,
    )
    if not added:
        raise conflict("already_listed", "This number is already on your do-not-call list.")
    now = datetime.now(UTC)
    for c in ctx.session.scalars(
        select(CampaignContact).where(CampaignContact.phone == phone, CampaignContact.status.in_(("pending", "retry")))
    ):
        c.status, c.block_reason, c.updated_at = "blocked", "do_not_call", now
    row = ctx.session.scalar(
        select(SuppressionEntry).where(SuppressionEntry.phone == phone, SuppressionEntry.removed_at.is_(None))
    )
    assert row is not None
    ctx.audit("suppression.added", resource_type="suppression", resource_id=str(row.id), reason=data.reason)
    return SuppressionOut.model_validate(row, from_attributes=True)


@router.post("/v1/suppression/{entry_id}/remove", response_model=SuppressionOut)
def remove_suppression(
    entry_id: UUID, data: UnsuppressIn, ctx: Ctx = Depends(require(Perm.CAMPAIGNS_APPROVE))
) -> SuppressionOut:
    row = ctx.session.scalar(
        select(SuppressionEntry).where(SuppressionEntry.id == entry_id, SuppressionEntry.tenant_id == ctx.tenant.id)
    )
    if not row:
        raise not_found()
    if row.removed_at is not None:
        raise conflict("already_removed", "This number was already taken off the list.")
    if row.reason == "opt_out" and len(data.reason.strip()) < 10:
        raise bad_request("reason_required", "The person asked not to be called. Say why they may be called again.")
    row.removed_at, row.removed_by_membership_id, row.removed_reason = datetime.now(UTC), ctx.membership.id, data.reason
    ctx.audit("suppression.removed", resource_type="suppression", resource_id=str(row.id), reason=data.reason[:200])
    return SuppressionOut.model_validate(row, from_attributes=True)
