# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Native workflows (M11, addendum H): booking calendars with holidays, appointments, leads with qualification and
CRM activity, and follow-ups. The same functions serve staff in the dashboard and agents through the tool gateway,
so a booking made on a call follows exactly the rules a booking made by hand does.

Every function runs inside the caller's tenant RLS context."""

import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import phonenumbers
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..m05_agents.schemas import DAYS
from ..m13_integrations.events import emit
from .models import Appointment, BookingCalendar, FollowUp, Holiday, Lead, LeadActivity

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L: easy to read out on a call


class WorkflowError(Exception):
    """A business rule said no. `code` is stable; `message` is safe to show or say."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Actor:
    tenant_id: UUID
    country: str  # tenant country, for phone numbers
    source: str  # call | chat | manual
    membership_id: UUID | None = None
    call_id: UUID | None = None


def reference(prefix: str) -> str:
    return f"{prefix}-" + "".join(secrets.choice(ALPHABET) for _ in range(6))


def phone(value: str | None, country: str) -> str | None:
    if not value or not value.strip():
        return None
    try:
        n = phonenumbers.parse(value, country)
    except phonenumbers.NumberParseException:
        raise WorkflowError("invalid_phone", "That phone number doesn't look right.") from None
    if not phonenumbers.is_valid_number(n):
        raise WorkflowError("invalid_phone", "That phone number doesn't look right.")
    return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)


def say_time(dt: datetime) -> str:
    """How a time is read out: "Tuesday 26 November at 10:30"."""
    return dt.strftime("%A %-d %B at %H:%M")


# ------------------------------------------------------------------------------------------------ holidays
def org_holiday(session: Session, day: date) -> Holiday | None:
    """A holiday that closes the whole organization (no calendar). Agents' business hours honour it too."""
    return session.scalar(select(Holiday).where(Holiday.calendar_id.is_(None), Holiday.day == day))


def holiday_for(session: Session, cal: BookingCalendar, day: date) -> Holiday | None:
    return session.scalar(
        select(Holiday).where(or_(Holiday.calendar_id.is_(None), Holiday.calendar_id == cal.id), Holiday.day == day)
    )


# ------------------------------------------------------------------------------------------------ availability
def _windows(cal: BookingCalendar, day: date) -> list[tuple[time, time]]:
    out = []
    for w in cal.weekly.get(DAYS[day.weekday()], []):
        out.append((time.fromisoformat(w["start"]), time.fromisoformat(w["end"])))
    return out


def slots(session: Session, cal: BookingCalendar, day: date, *, now: datetime | None = None) -> list[datetime]:
    """Free slot start times on `day` (calendar time zone): inside a weekly window, not a holiday, at least
    `min_notice_minutes` from now, within `horizon_days`, and not overlapping a booked appointment."""
    now = now or datetime.now(UTC)
    tz = ZoneInfo(cal.timezone)
    if cal.status != "active" or holiday_for(session, cal, day):
        return []
    earliest = now + timedelta(minutes=cal.min_notice_minutes)
    latest = now + timedelta(days=cal.horizon_days)
    step = timedelta(minutes=cal.slot_minutes)
    day_start = datetime.combine(day, time(0), tz)
    booked = session.execute(
        select(Appointment.starts_at, Appointment.ends_at).where(
            Appointment.calendar_id == cal.id,
            Appointment.status == "booked",
            Appointment.starts_at < day_start + timedelta(days=1, hours=1),
            Appointment.ends_at > day_start - timedelta(hours=1),
        )
    ).all()
    out = []
    for start, end in _windows(cal, day):
        t = datetime.combine(day, start, tz)
        stop = datetime.combine(day, end, tz)
        while t + step <= stop:
            if earliest <= t <= latest and not any(b0 < t + step and t < b1 for b0, b1 in booked):
                out.append(t)
            t += step
    return out


def availability(
    session: Session, cal: BookingCalendar, day: date | None, *, limit: int = 6, now: datetime | None = None
) -> dict[str, Any]:
    """What an agent reads out: up to `limit` free times on the asked day, or on the next day that has any."""
    now = now or datetime.now(UTC)
    tz = ZoneInfo(cal.timezone)
    today = now.astimezone(tz).date()
    asked = day or today
    if asked < today:
        raise WorkflowError("past_date", "That date has already passed.")
    h = holiday_for(session, cal, asked) if day is not None else None
    extra = {"asked_date_note": f"Closed on {asked.isoformat()} for {h.name}."} if h else {}
    for offset in range(0, min(cal.horizon_days, 31) + 1):
        d = asked + timedelta(days=offset)
        free = slots(session, cal, d, now=now)
        if free:
            return {
                "calendar": cal.name,
                "timezone": cal.timezone,
                "date": d.isoformat(),
                "asked_date_available": offset == 0,
                "slots": [{"start": t.strftime("%Y-%m-%dT%H:%M"), "say": say_time(t)} for t in free[:limit]],
                "more_slots_that_day": max(0, len(free) - limit),
            } | extra
    return {"calendar": cal.name, "date": asked.isoformat(), "slots": [], "note": "No free times soon."} | extra


def _local(cal: BookingCalendar, value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise WorkflowError("invalid_time", "Times must look like 2026-11-26T10:30.") from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(cal.timezone))
    return dt


def _check_slot(session: Session, cal: BookingCalendar, start: datetime, ignore: UUID | None = None) -> None:
    local = start.astimezone(ZoneInfo(cal.timezone))
    free = slots(session, cal, local.date())
    if ignore:  # rescheduling: the appointment's own current slot doesn't block its new one
        appt = session.get(Appointment, ignore)
        if appt and appt.starts_at.astimezone(ZoneInfo(cal.timezone)).date() == local.date():
            free = sorted(set(free) | {appt.starts_at.astimezone(ZoneInfo(cal.timezone))})
    if local not in free:
        raise WorkflowError("slot_unavailable", "That time isn't available. Check availability and pick another.")


def _lock(session: Session, cal_id: UUID) -> BookingCalendar:
    """Bookings on one calendar are serialized, so two callers can't take the same slot."""
    cal = session.scalar(select(BookingCalendar).where(BookingCalendar.id == cal_id).with_for_update())
    if not cal or cal.status != "active":
        raise WorkflowError("no_calendar", "Online booking isn't set up.")
    return cal


def appointment_payload(a: Appointment, cal: BookingCalendar) -> dict[str, Any]:
    local = a.starts_at.astimezone(ZoneInfo(cal.timezone))
    return {
        "id": str(a.id),
        "reference": a.reference,
        "calendar": cal.name,
        "start": local.strftime("%Y-%m-%dT%H:%M"),
        "say": say_time(local),
        "status": a.status,
        "customer_name": a.customer_name,
    }


def book(
    session: Session,
    actor: Actor,
    cal_id: UUID,
    *,
    start: str,
    name: str,
    phone_number: str | None = None,
    email: str | None = None,
    notes: str = "",
) -> Appointment:
    cal = _lock(session, cal_id)
    begins = _local(cal, start)
    _check_slot(session, cal, begins)
    a = Appointment(
        tenant_id=actor.tenant_id,
        calendar_id=cal.id,
        reference=reference("A"),
        starts_at=begins,
        ends_at=begins + timedelta(minutes=cal.slot_minutes),
        customer_name=name.strip()[:120],
        customer_phone=phone(phone_number, actor.country),
        customer_email=(email or None) and email.strip()[:200],
        notes=(notes or "")[:1000],
        source=actor.source,
        call_id=actor.call_id,
        created_by_membership_id=actor.membership_id,
    )
    try:
        with session.begin_nested():
            session.add(a)
            session.flush()
    except IntegrityError:
        raise WorkflowError("slot_unavailable", "That time was just taken. Please pick another.") from None
    emit(session, actor.tenant_id, "appointment.booked", appointment_payload(a, cal))
    return a


def find_appointment(session: Session, ref: str, phone_number: str | None, country: str) -> Appointment:
    """Callers identify a booking by its reference, and by its phone number when one was given at booking, so a
    reference alone read out by someone else can't change it."""
    a = session.scalar(select(Appointment).where(Appointment.reference == ref.strip().upper()))
    if not a:
        raise WorkflowError("not_found", "I couldn't find a booking with that reference.")
    if a.customer_phone and phone(phone_number, country) != a.customer_phone:
        raise WorkflowError("verification_failed", "That phone number doesn't match the booking.")
    return a


def reschedule(session: Session, actor: Actor, a: Appointment, new_start: str) -> Appointment:
    cal = _lock(session, a.calendar_id)
    if a.status != "booked":
        raise WorkflowError("not_active", "That booking isn't active any more.")
    begins = _local(cal, new_start)
    _check_slot(session, cal, begins, ignore=a.id)
    a.starts_at, a.ends_at = begins, begins + timedelta(minutes=cal.slot_minutes)
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError:
        raise WorkflowError("slot_unavailable", "That time was just taken. Please pick another.") from None
    emit(session, actor.tenant_id, "appointment.rescheduled", appointment_payload(a, cal))
    return a


def cancel(session: Session, actor: Actor, a: Appointment, reason: str | None = None) -> Appointment:
    cal = session.get(BookingCalendar, a.calendar_id)
    assert cal is not None
    if a.status != "booked":
        raise WorkflowError("not_active", "That booking isn't active any more.")
    a.status, a.cancelled_reason = "cancelled", (reason or None) and reason[:300]
    session.flush()
    emit(session, actor.tenant_id, "appointment.cancelled", appointment_payload(a, cal))
    return a


# ------------------------------------------------------------------------------------------------ leads
def qualification_score(lead: Lead) -> int:
    """Simple, explainable qualification: 25 points each for a stated need, budget, timeline and a way to reach
    the person. Shown with its parts in the dashboard."""
    return 25 * sum(bool(x) for x in (lead.interest, lead.budget, lead.timeline, lead.phone or lead.email))


def create_lead(
    session: Session,
    actor: Actor,
    *,
    name: str,
    phone_number: str | None = None,
    email: str | None = None,
    company: str = "",
    interest: str = "",
    budget: str = "",
    timeline: str = "",
    callback_at: datetime | None = None,
    note: str = "",
) -> tuple[Lead, FollowUp | None]:
    lead = Lead(
        tenant_id=actor.tenant_id,
        name=name.strip()[:120],
        phone=phone(phone_number, actor.country),
        email=(email or None) and email.strip()[:200],
        company=company[:120],
        interest=interest[:1000],
        budget=budget[:120],
        timeline=timeline[:120],
        source=actor.source,
        call_id=actor.call_id,
        owner_membership_id=actor.membership_id,
    )
    lead.score = qualification_score(lead)
    session.add(lead)
    session.flush()
    how = {"call": "a call", "chat": "a test chat", "manual": "the dashboard"}[actor.source]
    session.add(
        LeadActivity(
            tenant_id=actor.tenant_id,
            lead_id=lead.id,
            kind="created",
            body=f"Created from {how}." + (f" {note}" if note else ""),
            call_id=actor.call_id,
            created_by_membership_id=actor.membership_id,
        )
    )
    fu = None
    if callback_at is not None:
        fu = add_follow_up(session, actor, due_at=callback_at, lead_id=lead.id, note="Call back: requested on a call")
    emit(
        session,
        actor.tenant_id,
        "lead.created",
        {"id": str(lead.id), "name": lead.name, "score": lead.score, "source": lead.source},
    )
    return lead, fu


def add_follow_up(
    session: Session,
    actor: Actor,
    *,
    due_at: datetime,
    channel: str = "call",
    note: str = "",
    lead_id: UUID | None = None,
    ticket_id: UUID | None = None,
    appointment_id: UUID | None = None,
    assignee: UUID | None = None,
) -> FollowUp:
    if due_at.tzinfo is None:
        raise WorkflowError("invalid_time", "A follow-up time needs a time zone.")
    fu = FollowUp(
        tenant_id=actor.tenant_id,
        lead_id=lead_id,
        ticket_id=ticket_id,
        appointment_id=appointment_id,
        due_at=due_at,
        channel=channel,
        note=note[:500],
        source=actor.source,
        call_id=actor.call_id,
        assignee_membership_id=assignee,
        created_by_membership_id=actor.membership_id,
    )
    session.add(fu)
    session.flush()
    if lead_id:
        session.add(
            LeadActivity(
                tenant_id=actor.tenant_id,
                lead_id=lead_id,
                kind="follow_up",
                body=f"Follow-up ({channel}) due {due_at.isoformat(timespec='minutes')}. {note}".strip(),
                call_id=actor.call_id,
                created_by_membership_id=actor.membership_id,
            )
        )
    emit(
        session,
        actor.tenant_id,
        "follow_up.created",
        {"id": str(fu.id), "due_at": due_at.isoformat(), "channel": channel, "lead_id": lead_id and str(lead_id)},
    )
    return fu
