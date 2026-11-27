# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Vendor eligibility for PHI (M21): which AI providers may receive health information today, and why not."""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from ...core.context import Ctx, require
from ...core.permissions import Perm
from ..m03_ai.models import Provider
from ..m19_healthcare.models import VendorRecord
from .service import ai_provider_eligible, baa_in_force, current_record

router = APIRouter(tags=["vendors"])


class VendorEligibilityOut(BaseModel):
    vendor_type: str
    vendor_key: str
    name: str
    kinds: list[str]
    eligible: bool
    reason: str
    baa_expires_on: date | None


@router.get("/v1/vendors/eligibility", response_model=list[VendorEligibilityOut])
def eligibility(ctx: Ctx = Depends(require(Perm.HEALTHCARE_READ))) -> list[VendorEligibilityOut]:
    out: list[VendorEligibilityOut] = []
    for p in ctx.session.scalars(select(Provider).where(Provider.status == "active").order_by(Provider.name)):
        e = ai_provider_eligible(ctx.session, p)
        out.append(
            VendorEligibilityOut(
                vendor_type="ai_provider",
                vendor_key=p.key,
                name=p.name,
                kinds=list(p.kinds or []),
                eligible=e.ok,
                reason=e.reason,
                baa_expires_on=e.record.expires_on if e.record else None,
            )
        )
    keys = ctx.session.execute(
        select(VendorRecord.vendor_type, VendorRecord.vendor_key, VendorRecord.vendor_name)
        .where(VendorRecord.vendor_type != "ai_provider")
        .distinct()
    ).all()
    for vtype, vkey, vname in sorted(keys, key=lambda r: (r[0], r[2])):
        e = baa_in_force(current_record(ctx.session, vtype, vkey))
        out.append(
            VendorEligibilityOut(
                vendor_type=vtype,
                vendor_key=vkey,
                name=vname,
                kinds=[],
                eligible=e.ok,
                reason=e.reason,
                baa_expires_on=e.record.expires_on if e.record else None,
            )
        )
    return out
