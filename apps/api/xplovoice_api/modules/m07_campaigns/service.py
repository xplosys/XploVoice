# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Campaign bookkeeping: what happens to a contact after each attempt (retry policy), and campaign completion."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..m08_calls.models import Call
from .models import Campaign, CampaignContact, DialAttempt

OUTCOME_FOR_STATE = {
    "busy": "busy",
    "no_answer": "no_answer",
    "failed": "failed",
    "cancelled": "cancelled",
}
OPEN = ("pending", "retry", "calling")


def attempt_finished(s: Session, call: Call) -> None:
    attempt = s.scalar(select(DialAttempt).where(DialAttempt.call_id == call.id).with_for_update())
    if attempt is None or attempt.outcome is not None:
        return
    now = datetime.now(UTC)
    outcome = "answered" if call.answered_at else OUTCOME_FOR_STATE.get(call.state, "failed")
    attempt.outcome, attempt.ended_at = outcome, now
    contact = s.get(CampaignContact, attempt.contact_id)
    campaign = s.get(Campaign, attempt.campaign_id)
    assert contact is not None and campaign is not None
    contact.last_outcome, contact.updated_at = outcome, now
    if contact.status == "calling":
        if outcome == "answered":
            contact.status = "completed"
        elif contact.attempts >= campaign.max_attempts:
            contact.status = "exhausted"
        else:
            contact.status = "retry"
            contact.next_attempt_at = now + timedelta(minutes=campaign.retry_minutes)
    maybe_complete(s, campaign)


def maybe_complete(s: Session, campaign: Campaign) -> None:
    if campaign.status != "running":
        return
    left = s.scalar(
        select(func.count())
        .select_from(CampaignContact)
        .where(CampaignContact.campaign_id == campaign.id, CampaignContact.status.in_(OPEN))
    )
    if not left:
        campaign.status, campaign.updated_at = "completed", datetime.now(UTC)
