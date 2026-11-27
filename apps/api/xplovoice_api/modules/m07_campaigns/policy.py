# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Outbound policy engine (addendum I, HLD v1.0 section 7). Every outbound call and every transfer is checked
before any carrier request, and the decision is stored with each check's result.

- block: the call must not happen (emergency stop, destination not allowed, premium number, do-not-call, no
  consent, attempts used up).
- defer: not now (outside the calling window, concurrency, rate or daily limit); the dialer tries again later.
- allow.

Calling windows: the campaign's own window, never wider than a per-country default in the person's local time
(India 09:00-21:00, US 08:00-21:00). These defaults are a starting point from common guidance, not legal advice:
the Phase 0 legal review (TRAI/TCCCPR, TCPA/DNC) is still open."""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING
from uuid import UUID
from zoneinfo import ZoneInfo

import phonenumbers
from phonenumbers import timezone as pn_timezone
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ..m04_telephony.models import DestinationPolicy, TelephonyUsage
from ..m04_telephony.service import live_calls, live_outbound
from ..m08_calls import lifecycle
from ..m08_calls.models import Call
from ..m15_usage import billing
from ..m19_healthcare.mode import phi_mode, policy_in_force
from ..m22_consent.service import has_consent, is_suppressed
from .models import PolicyDecision

if TYPE_CHECKING:
    from .models import Campaign, CampaignContact

COUNTRY_WINDOWS = {"IN": (time(9, 0), time(21, 0)), "US": (time(8, 0), time(21, 0))}
DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
BLOCKED_TYPES = {phonenumbers.PhoneNumberType.PREMIUM_RATE, phonenumbers.PhoneNumberType.SHARED_COST}


@dataclass
class Check:
    check: str
    ok: bool
    detail: str = ""


@dataclass
class Decision:
    decision: str  # allow | defer | block
    reason: str | None = None
    checks: list[Check] = field(default_factory=list)
    retry_at: datetime | None = None

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"


def destination_checks(policy: DestinationPolicy, phone: str) -> list[Check]:
    """Toll-fraud and destination checks shared by outbound calls and transfers."""
    out = [Check("platform_enabled", get_settings().telephony_enabled, "Telephony is paused for the platform.")]
    out.append(Check("organisation_enabled", policy.telephony_enabled, "Your organisation has paused phone calls."))
    try:
        n = phonenumbers.parse(phone)
        valid = phonenumbers.is_valid_number(n)
    except phonenumbers.NumberParseException:
        n, valid = None, False
    out.append(Check("valid_number", valid, "Not a valid phone number."))
    if not valid or n is None:
        return out
    region = phonenumbers.region_code_for_number(n)
    out.append(
        Check(
            "country_allowed", region in policy.allowed_countries, f"Calls to {region} aren't allowed by your policy."
        )
    )
    premium = phonenumbers.number_type(n) in BLOCKED_TYPES
    out.append(Check("not_premium", not (premium and policy.block_premium), "Premium-rate numbers are blocked."))
    return out


def recipient_zones(phone: str, contact_tz: str | None, campaign_tz: str) -> list[ZoneInfo]:
    if contact_tz:
        return [ZoneInfo(contact_tz)]
    try:
        zones = [z for z in pn_timezone.time_zones_for_number(phonenumbers.parse(phone)) if z != "Etc/Unknown"]
    except phonenumbers.NumberParseException:
        zones = []
    return [ZoneInfo(z) for z in zones] or [ZoneInfo(campaign_tz)]


def window_open(campaign: "Campaign", phone: str, contact_tz: str | None, at: datetime) -> bool:
    """Open only if it is inside the window in every time zone the person may be in."""
    region = phonenumbers.region_code_for_number(phonenumbers.parse(phone))
    c_start, c_end = COUNTRY_WINDOWS.get(region, (time(9, 0), time(20, 0)))
    start, end = max(campaign.window_start, c_start), min(campaign.window_end, c_end)
    for z in recipient_zones(phone, contact_tz, campaign.timezone):
        local = at.astimezone(z)
        if DAY_KEYS[local.weekday()] not in campaign.days or not (start <= local.time() < end):
            return False
    return True


def next_window(campaign: "Campaign", phone: str, contact_tz: str | None, at: datetime) -> datetime | None:
    t = at.replace(second=0, microsecond=0)
    for _ in range(8 * 24 * 4):  # 15-minute steps, up to 8 days
        t += timedelta(minutes=15)
        if window_open(campaign, phone, contact_tz, t):
            return t
    return None


def evaluate_outbound(
    s: Session, policy: DestinationPolicy, campaign: "Campaign", contact: "CampaignContact", now: datetime | None = None
) -> Decision:
    now = now or datetime.now(UTC)
    checks = destination_checks(policy, contact.phone)
    failed = next((c for c in checks if not c.ok), None)
    if failed:
        return Decision("block", failed.check, checks)
    checks.append(Check("campaign_running", campaign.status == "running", "The campaign isn't running."))
    if not checks[-1].ok:
        return Decision("defer", "campaign_running", checks, now + timedelta(minutes=5))
    checks.append(Check("not_on_do_not_call_list", not is_suppressed(s, contact.phone), "On your do-not-call list."))
    if not checks[-1].ok:
        return Decision("block", "do_not_call", checks)
    checks.append(
        Check("consent", has_consent(s, contact.phone, "outbound_calls"), "No recorded consent to be called.")
    )
    if not checks[-1].ok:
        return Decision("block", "no_consent", checks)
    checks.append(
        Check("attempts_left", contact.attempts < campaign.max_attempts, "All attempts for this contact are used.")
    )
    if not checks[-1].ok:
        return Decision("block", "attempts_used", checks)
    if phi_mode(s):
        allowed = policy_in_force(s).allow_outbound_campaigns
        checks.append(
            Check("healthcare_policy", allowed, "Your healthcare policy doesn't allow outbound campaign calls.")
        )
        if not allowed:
            return Decision("block", "healthcare_policy", checks)
    blocked = billing.admission(s, "call")
    checks.append(Check("billing", blocked is None, blocked.message if blocked else "Billing allows calls."))
    if blocked is not None:  # spending limit, quota or an overdue invoice: wait, the person may fix it
        return Decision("defer", "billing", checks, now + timedelta(minutes=30))
    open_now = window_open(campaign, contact.phone, contact.timezone, now)
    checks.append(Check("calling_window", open_now, "Outside the calling window in the person's local time."))
    if not open_now:
        return Decision("defer", "calling_window", checks, next_window(campaign, contact.phone, contact.timezone, now))
    org_ok = live_outbound(s, campaign.tenant_id) < policy.max_concurrent_outbound and (
        live_calls(s, campaign.tenant_id) < billing.max_concurrent_calls(s)
    )
    checks.append(Check("organisation_concurrency", org_ok, "Your organisation's call limit is reached."))
    if not org_ok:
        return Decision("defer", "organisation_concurrency", checks, now + timedelta(seconds=60))
    mine = (
        s.scalar(
            select(func.count())
            .select_from(Call)
            .where(Call.campaign_id == campaign.id, Call.state.not_in(lifecycle.TERMINAL_STATES))
        )
        or 0
    )
    checks.append(
        Check("campaign_concurrency", mine < campaign.max_concurrent, "The campaign's call limit is reached.")
    )
    if not checks[-1].ok:
        return Decision("defer", "campaign_concurrency", checks, now + timedelta(seconds=30))
    recent = (
        s.scalar(
            select(func.count())
            .select_from(Call)
            .where(Call.campaign_id == campaign.id, Call.created_at > now - timedelta(seconds=60))
        )
        or 0
    )
    checks.append(
        Check("rate", recent < campaign.calls_per_minute, "The campaign's calls-per-minute limit is reached.")
    )
    if not checks[-1].ok:
        return Decision("defer", "rate", checks, now + timedelta(seconds=20))
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    used = (
        s.scalar(
            select(func.coalesce(func.sum(TelephonyUsage.billed_seconds), 0)).where(
                TelephonyUsage.direction == "outbound", TelephonyUsage.created_at >= day_start
            )
        )
        or 0
    )
    under = used < policy.daily_outbound_minutes * 60
    checks.append(Check("daily_minutes", under, "Today's outbound minutes cap is reached."))
    if not under:
        return Decision("defer", "daily_minutes", checks, day_start + timedelta(days=1, minutes=5))
    return Decision("allow", None, checks)


def record(
    s: Session,
    d: Decision,
    *,
    tenant_id: UUID,
    phone: str,
    purpose: str,
    campaign_id: UUID | None = None,
    contact_id: UUID | None = None,
    call_id: UUID | None = None,
) -> PolicyDecision:
    row = PolicyDecision(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        contact_id=contact_id,
        call_id=call_id,
        phone=phone,
        purpose=purpose,
        decision=d.decision,
        reason=d.reason,
        checks=[asdict(c) for c in d.checks],
    )
    s.add(row)
    s.flush()
    return row
