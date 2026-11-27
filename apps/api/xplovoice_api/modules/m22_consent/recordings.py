# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Recording access check (M22, LLD v1.3 section 5). Answers whether the signed-in person may play a call's
recording, and why. In a healthcare organisation it needs phi:read and the caller's recorded consent, and every
check is written to the PHI access log. Recording storage itself is awaiting configuration, so no audio exists yet:
the check is in place for when it does."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...core.context import Ctx, require
from ...core.errors import not_found
from ...core.permissions import Perm, has
from ..m08_calls.models import Call
from ..m19_healthcare.mode import phi_mode
from ..m23_audit.service import log
from .models import ConsentRecord

router = APIRouter(tags=["consent"])


class AccessIn(BaseModel):
    purpose: Literal["quality_review", "dispute", "patient_request", "legal", "other"] = "quality_review"
    note: str = Field(default="", max_length=200)


class AccessOut(BaseModel):
    allowed: bool
    reason: str
    recording_available: bool
    consent_recorded: bool


@router.post("/v1/recordings/{call_id}/access-check", response_model=AccessOut)
def access_check(call_id: UUID, data: AccessIn, ctx: Ctx = Depends(require(Perm.CALLS_READ))) -> AccessOut:
    call = ctx.session.scalar(select(Call).where(Call.id == call_id, Call.tenant_id == ctx.tenant.id))
    if call is None:
        raise not_found()
    consent = (
        ctx.session.scalar(
            select(ConsentRecord.id)
            .where(
                ConsentRecord.call_id == call.id,
                ConsentRecord.purpose == "recording",
                ConsentRecord.status == "granted",
                ConsentRecord.revoked_at.is_(None),
            )
            .limit(1)
        )
        is not None
    )
    healthcare = phi_mode(ctx.session)
    if healthcare and not has(ctx.membership.role, Perm.PHI_READ):
        allowed, reason = False, "Your role can't open health information."
    elif healthcare and not consent:
        allowed, reason = False, "The caller did not consent to recording on this call."
    elif call.content_purged_at is not None:
        allowed, reason = False, "This call's content was removed under your retention schedule."
    else:
        allowed, reason = True, "Allowed."
    if healthcare:
        log(
            ctx,
            "access_check",
            "call_recording",
            str(call.id),
            allowed=allowed,
            purpose=data.purpose,
            reason=None if allowed else reason,
        )
    ctx.audit("recording.access_checked", resource_type="call", resource_id=str(call.id), allowed=allowed)
    return AccessOut(allowed=allowed, reason=reason, recording_available=False, consent_recorded=consent)
