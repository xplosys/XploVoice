# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Consent records and the do-not-call list (M22-core, split from M22 so it lands before outbound campaigns:
Phase 0 conflict X-2, CR-023).

A person can be called by a campaign only with a granted, unrevoked consent for outbound calls, and never while
their number is on the organisation's do-not-call list. Saying "stop calling me" on a call adds the number to the
list and revokes the consent at once. Records are never deleted: revoking and removing keep who and when."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import ConsentRecord, SuppressionEntry


def is_suppressed(s: Session, phone: str) -> bool:
    return (
        s.scalar(
            select(SuppressionEntry.id).where(SuppressionEntry.phone == phone, SuppressionEntry.removed_at.is_(None))
        )
        is not None
    )


def has_consent(s: Session, phone: str, purpose: str) -> bool:
    latest = s.scalar(
        select(ConsentRecord)
        .where(ConsentRecord.phone == phone, ConsentRecord.purpose == purpose)
        .order_by(ConsentRecord.captured_at.desc(), ConsentRecord.id)
        .limit(1)
    )
    return latest is not None and latest.status == "granted" and latest.revoked_at is None


def record_consent(
    s: Session,
    *,
    tenant_id: UUID,
    phone: str,
    purpose: str,
    status: str,
    basis: str,
    source: str,
    evidence: str = "",
    call_id: UUID | None = None,
    membership_id: UUID | None = None,
) -> ConsentRecord:
    c = ConsentRecord(
        tenant_id=tenant_id,
        phone=phone,
        purpose=purpose,
        status=status,
        basis=basis,
        source=source,
        evidence=evidence[:1000],
        call_id=call_id,
        captured_by_membership_id=membership_id,
        captured_at=datetime.now(UTC),
    )
    s.add(c)
    s.flush()
    return c


def revoke(s: Session, phone: str, purpose: str, reason: str) -> int:
    rows = s.scalars(
        select(ConsentRecord).where(
            ConsentRecord.phone == phone,
            ConsentRecord.purpose == purpose,
            ConsentRecord.status == "granted",
            ConsentRecord.revoked_at.is_(None),
        )
    ).all()
    now = datetime.now(UTC)
    for c in rows:
        c.status, c.revoked_at, c.revoked_reason = "revoked", now, reason[:200]
    return len(rows)


def suppress(
    s: Session,
    *,
    tenant_id: UUID,
    phone: str,
    reason: str,
    source: str,
    note: str = "",
    call_id: UUID | None = None,
    membership_id: UUID | None = None,
) -> bool:
    """Adds a number to the do-not-call list. Returns False if it was already on it."""
    row = s.execute(
        insert(SuppressionEntry)
        .values(
            tenant_id=tenant_id,
            phone=phone,
            reason=reason,
            source=source,
            note=note[:500],
            call_id=call_id,
            created_by_membership_id=membership_id,
        )
        .on_conflict_do_nothing(
            index_elements=["tenant_id", "phone"], index_where=SuppressionEntry.removed_at.is_(None)
        )
        .returning(SuppressionEntry.id)
    ).first()
    return row is not None


def opt_out(s: Session, *, tenant_id: UUID, phone: str, call_id: UUID | None, said: str = "") -> None:
    """The person asked not to be called again: do-not-call list, consent revoked, pending campaign calls
    stopped. Runs on every channel and every campaign of the organisation."""
    from ..m07_campaigns.models import CampaignContact

    suppress(s, tenant_id=tenant_id, phone=phone, reason="opt_out", source="call", note=said[:200], call_id=call_id)
    revoke(s, phone, "outbound_calls", "Asked not to be called again")
    for c in s.scalars(
        select(CampaignContact).where(
            CampaignContact.phone == phone, CampaignContact.status.in_(("pending", "retry", "calling"))
        )
    ):
        c.status, c.block_reason, c.updated_at = "opted_out", "Asked not to be called again", datetime.now(UTC)
