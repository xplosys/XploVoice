# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""BAA and vendor governance (M21). A vendor may receive PHI only while its latest record is a signed BAA that has
not expired. For AI providers the catalog flag (`phi_eligible`, which itself needs `baa_status = 'signed'`) must
also be on: the record is the evidence, the flag is the platform's decision to use it. Fallback providers pass the
same check (LLD v1.3 section 7), because routing applies it to every candidate."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..m19_healthcare.models import VendorRecord


@dataclass
class Eligibility:
    ok: bool
    reason: str
    record: VendorRecord | None


def current_record(s: Session, vendor_type: str, vendor_key: str) -> VendorRecord | None:
    return s.scalar(
        select(VendorRecord)
        .where(VendorRecord.vendor_type == vendor_type, VendorRecord.vendor_key == vendor_key)
        .order_by(VendorRecord.created_at.desc(), VendorRecord.id.desc())
        .limit(1)
    )


def baa_in_force(rec: VendorRecord | None, today: date | None = None) -> Eligibility:
    today = today or datetime.now(UTC).date()
    if rec is None:
        return Eligibility(False, "no BAA on record", None)
    if rec.baa_status != "signed":
        return Eligibility(False, "BAA terminated", rec)
    if rec.expires_on is not None and rec.expires_on < today:
        return Eligibility(False, f"BAA expired on {rec.expires_on.isoformat()}", rec)
    return Eligibility(True, "signed BAA on record", rec)


def ai_provider_eligible(s: Session, provider: object) -> Eligibility:
    if not getattr(provider, "phi_eligible", False):
        return Eligibility(False, "not approved for health information (no signed BAA)", None)
    e = baa_in_force(current_record(s, "ai_provider", provider.key))  # type: ignore[attr-defined]
    if not e.ok:
        return Eligibility(False, f"not approved for health information ({e.reason})", e.record)
    return e
