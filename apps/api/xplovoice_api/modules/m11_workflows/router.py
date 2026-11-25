# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Native workflows API (M11): booking calendars, holidays, appointments, leads with CRM activity, follow-ups.
Staff use these screens to run the work agents create on calls; the same service functions back the tools."""

from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from ...core.context import Ctx, require
from ...core.errors import bad_request, conflict, not_found
from ...core.permissions import Perm
from ..m05_agents.schemas import DAYS, BusinessHours, Window
from ..m13_integrations.events import emit
from . import service as wf
from .models import Appointment, BookingCalendar, FollowUp, Holiday, Lead, LeadActivity

router = APIRouter(tags=["workflows"])


def _actor(ctx: Ctx) -> wf.Actor:
    return wf.Actor(
        tenant_id=ctx.tenant.id, country=ctx.tenant.country_code, source="manual", membership_id=ctx.membership.id
    )


def _fail(e: wf.WorkflowError) -> Exception:
    return (
        conflict(e.code, e.message) if e.code in ("slot_unavailable", "not_active") else bad_request(e.code, e.message)
    )


# ---------------------------------------------------------------------------------------------------- calendars
class CalendarIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    slot_minutes: int = Field(default=30, ge=5, le=240)
    weekly: dict[str, list[Window]] | None = None
    min_notice_minutes: int = Field(default=60, ge=0, le=10080)
    horizon_days: int = Field(default=30, ge=1, le=180)
    status: Literal["active", "archived"] = "active"

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        return BusinessHours(timezone=v).timezone  # same validation as agent business hours

    @field_validator("weekly")
    @classmethod
    def _weekly(cls, v: dict[str, list[Window]] | None) -> dict[str, list[Window]] | None:
        if v is None:
            return None
        return BusinessHours(weekly=v).weekly  # type: ignore[arg-type]


class CalendarOut(BaseModel):
    id: UUID
    name: str
    timezone: str
    slot_minutes: int
    weekly: dict[str, list[Window]]
    min_notice_minutes: int
    horizon_days: int
    status: str


def _cal(ctx: Ctx, cal_id: UUID) -> BookingCalendar:
    cal = ctx.session.scalar(
        select(BookingCalendar).where(BookingCalendar.id == cal_id, BookingCalendar.tenant_id == ctx.tenant.id)
    )
    if not cal:
        raise not_found()
    return cal


def _cal_out(c: BookingCalendar) -> CalendarOut:
    return CalendarOut(
        id=c.id,
        name=c.name,
        timezone=c.timezone,
        slot_minutes=c.slot_minutes,
        weekly={d: c.weekly.get(d, []) for d in DAYS},
        min_notice_minutes=c.min_notice_minutes,
        horizon_days=c.horizon_days,
        status=c.status,
    )


def _weekly_json(w: dict[str, list[Window]] | None) -> dict[str, Any]:
    w = w or BusinessHours().weekly  # type: ignore[assignment]
    return {d: [x.model_dump() for x in w.get(d, [])] for d in DAYS}  # type: ignore[union-attr]


@router.get("/v1/booking-calendars", response_model=list[CalendarOut])
def list_calendars(ctx: Ctx = Depends(require(Perm.WORKFLOWS_READ))) -> list[CalendarOut]:
    rows = ctx.session.scalars(select(BookingCalendar).order_by(BookingCalendar.status, BookingCalendar.name))
    return [_cal_out(c) for c in rows]


@router.post("/v1/booking-calendars", response_model=CalendarOut, status_code=status.HTTP_201_CREATED)
def create_calendar(data: CalendarIn, ctx: Ctx = Depends(require(Perm.WORKFLOWS_MANAGE))) -> CalendarOut:
    c = BookingCalendar(
        tenant_id=ctx.tenant.id,
        name=data.name.strip(),
        timezone=data.timezone,
        slot_minutes=data.slot_minutes,
        weekly=_weekly_json(data.weekly),
        min_notice_minutes=data.min_notice_minutes,
        horizon_days=data.horizon_days,
    )
    ctx.session.add(c)
    ctx.session.flush()
    ctx.audit("calendar.created", resource_type="booking_calendar", resource_id=str(c.id))
    return _cal_out(c)


@router.put("/v1/booking-calendars/{cal_id}", response_model=CalendarOut)
def update_calendar(cal_id: UUID, data: CalendarIn, ctx: Ctx = Depends(require(Perm.WORKFLOWS_MANAGE))) -> CalendarOut:
    c = _cal(ctx, cal_id)
    c.name, c.timezone, c.slot_minutes = data.name.strip(), data.timezone, data.slot_minutes
    c.weekly = _weekly_json(data.weekly)
    c.min_notice_minutes, c.horizon_days, c.status = data.min_notice_minutes, data.horizon_days, data.status
    ctx.session.flush()
    ctx.audit("calendar.updated", resource_type="booking_calendar", resource_id=str(c.id))
    return _cal_out(c)


@router.get("/v1/booking-calendars/{cal_id}/availability")
def calendar_availability(
    cal_id: UUID, day: date | None = None, ctx: Ctx = Depends(require(Perm.WORKFLOWS_READ))
) -> dict[str, Any]:
    try:
        return wf.availability(ctx.session, _cal(ctx, cal_id), day, limit=48)
    except wf.WorkflowError as e:
        raise _fail(e) from None


# ---------------------------------------------------------------------------------------------------- holidays
class HolidayIn(BaseModel):
    day: date
    name: str = Field(min_length=1, max_length=120)
    calendar_id: UUID | None = None  # none: the whole organization, agents' business hours included


class HolidayOut(BaseModel):
    id: UUID
    day: date
    name: str
    calendar_id: UUID | None


@router.get("/v1/holidays", response_model=list[HolidayOut])
def list_holidays(ctx: Ctx = Depends(require(Perm.WORKFLOWS_READ))) -> list[HolidayOut]:
    rows = ctx.session.scalars(select(Holiday).order_by(Holiday.day))
    return [HolidayOut(id=h.id, day=h.day, name=h.name, calendar_id=h.calendar_id) for h in rows]


@router.post("/v1/holidays", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
def add_holiday(data: HolidayIn, ctx: Ctx = Depends(require(Perm.WORKFLOWS_MANAGE))) -> HolidayOut:
    if data.calendar_id:
        _cal(ctx, data.calendar_id)
    if ctx.session.scalar(
        select(Holiday.id).where(
            Holiday.day == data.day,
            Holiday.calendar_id.is_(None) if data.calendar_id is None else Holiday.calendar_id == data.calendar_id,
        )
    ):
        raise conflict("duplicate", "That day is already a holiday.")
    h = Holiday(tenant_id=ctx.tenant.id, day=data.day, name=data.name.strip(), calendar_id=data.calendar_id)
    ctx.session.add(h)
    ctx.session.flush()
    ctx.audit("holiday.added", resource_type="holiday", resource_id=str(h.id), day=data.day.isoformat())
    return HolidayOut(id=h.id, day=h.day, name=h.name, calendar_id=h.calendar_id)


@router.delete("/v1/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_holiday(holiday_id: UUID, ctx: Ctx = Depends(require(Perm.WORKFLOWS_MANAGE))) -> Response:
    h = ctx.session.scalar(select(Holiday).where(Holiday.id == holiday_id, Holiday.tenant_id == ctx.tenant.id))
    if not h:
        raise not_found()
    ctx.session.delete(h)
    ctx.audit("holiday.removed", resource_type="holiday", resource_id=str(holiday_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------------------------------- appointments
class AppointmentIn(BaseModel):
    calendar_id: UUID
    start: str = Field(description="YYYY-MM-DDTHH:MM in the calendar's time zone")
    customer_name: str = Field(min_length=1, max_length=120)
    customer_phone: str | None = Field(default=None, max_length=30)
    customer_email: str | None = Field(default=None, max_length=200)
    notes: str = Field(default="", max_length=1000)


class RescheduleIn(BaseModel):
    start: str


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class AppointmentStatusIn(BaseModel):
    status: Literal["completed", "no_show"]


class AppointmentOut(BaseModel):
    id: UUID
    reference: str
    calendar_id: UUID
    calendar: str
    timezone: str
    starts_at: datetime
    ends_at: datetime
    local_start: str
    status: str
    customer_name: str
    customer_phone: str | None
    customer_email: str | None
    notes: str
    source: str
    call_id: UUID | None
    cancelled_reason: str | None
    created_at: datetime


def _appt_out(a: Appointment, c: BookingCalendar) -> AppointmentOut:
    local = a.starts_at.astimezone(ZoneInfo(c.timezone))
    return AppointmentOut(
        id=a.id,
        reference=a.reference,
        calendar_id=c.id,
        calendar=c.name,
        timezone=c.timezone,
        starts_at=a.starts_at,
        ends_at=a.ends_at,
        local_start=local.strftime("%Y-%m-%dT%H:%M"),
        status=a.status,
        customer_name=a.customer_name,
        customer_phone=a.customer_phone,
        customer_email=a.customer_email,
        notes=a.notes,
        source=a.source,
        call_id=a.call_id,
        cancelled_reason=a.cancelled_reason,
        created_at=a.created_at,
    )


def _appt(ctx: Ctx, appt_id: UUID) -> tuple[Appointment, BookingCalendar]:
    a = ctx.session.scalar(select(Appointment).where(Appointment.id == appt_id, Appointment.tenant_id == ctx.tenant.id))
    if not a:
        raise not_found()
    c = ctx.session.get(BookingCalendar, a.calendar_id)
    assert c is not None
    return a, c


@router.get("/v1/appointments", response_model=list[AppointmentOut])
def list_appointments(
    status_: str | None = Query(default=None, alias="status"),
    upcoming: bool = False,
    call_id: UUID | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    ctx: Ctx = Depends(require(Perm.WORKFLOWS_READ)),
) -> list[AppointmentOut]:
    q = select(Appointment, BookingCalendar).join(BookingCalendar, BookingCalendar.id == Appointment.calendar_id)
    if status_:
        q = q.where(Appointment.status == status_)
    if upcoming:
        q = q.where(Appointment.starts_at >= datetime.now(UTC))
    if call_id:
        q = q.where(Appointment.call_id == call_id)
    rows = ctx.session.execute(
        q.order_by(Appointment.starts_at if upcoming else Appointment.starts_at.desc()).limit(limit)
    ).all()
    return [_appt_out(a, c) for a, c in rows]


@router.post("/v1/appointments", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(data: AppointmentIn, ctx: Ctx = Depends(require(Perm.WORKFLOWS_MANAGE))) -> AppointmentOut:
    cal = _cal(ctx, data.calendar_id)
    try:
        a = wf.book(
            ctx.session,
            _actor(ctx),
            cal.id,
            start=data.start,
            name=data.customer_name,
            phone_number=data.customer_phone,
            email=data.customer_email,
            notes=data.notes,
        )
    except wf.WorkflowError as e:
        raise _fail(e) from None
    ctx.audit("appointment.booked", resource_type="appointment", resource_id=str(a.id))
    return _appt_out(a, cal)


@router.post("/v1/appointments/{appt_id}/reschedule", response_model=AppointmentOut)
def reschedule_appointment(
    appt_id: UUID, data: RescheduleIn, ctx: Ctx = Depends(require(Perm.WORKFLOWS_MANAGE))
) -> AppointmentOut:
    a, c = _appt(ctx, appt_id)
    try:
        wf.reschedule(ctx.session, _actor(ctx), a, data.start)
    except wf.WorkflowError as e:
        raise _fail(e) from None
    ctx.audit("appointment.rescheduled", resource_type="appointment", resource_id=str(a.id))
    return _appt_out(a, c)


@router.post("/v1/appointments/{appt_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(
    appt_id: UUID, data: CancelIn, ctx: Ctx = Depends(require(Perm.WORKFLOWS_MANAGE))
) -> AppointmentOut:
    a, c = _appt(ctx, appt_id)
    try:
        wf.cancel(ctx.session, _actor(ctx), a, data.reason)
    except wf.WorkflowError as e:
        raise _fail(e) from None
    ctx.audit("appointment.cancelled", resource_type="appointment", resource_id=str(a.id))
    return _appt_out(a, c)


@router.post("/v1/appointments/{appt_id}/status", response_model=AppointmentOut)
def set_appointment_status(
    appt_id: UUID, data: AppointmentStatusIn, ctx: Ctx = Depends(require(Perm.WORKFLOWS_MANAGE))
) -> AppointmentOut:
    a, c = _appt(ctx, appt_id)
    if a.status != "booked":
        raise conflict("not_active", "Only a booked appointment can be marked.")
    a.status = data.status
    ctx.session.flush()
    ctx.audit(f"appointment.{data.status}", resource_type="appointment", resource_id=str(a.id))
    return _appt_out(a, c)


# ---------------------------------------------------------------------------------------------------- leads
class LeadIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=200)
    company: str = Field(default="", max_length=120)
    interest: str = Field(default="", max_length=1000)
    budget: str = Field(default="", max_length=120)
    timeline: str = Field(default="", max_length=120)


class LeadPatch(BaseModel):
    status: Literal["new", "contacted", "qualified", "won", "lost"] | None = None
    owner_membership_id: UUID | None = None


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    kind: Literal["note", "call"] = "note"


class ActivityOut(BaseModel):
    kind: str
    body: str
    call_id: UUID | None
    created_at: datetime


class FollowUpOut(BaseModel):
    id: UUID
    due_at: datetime
    channel: str
    note: str
    status: str
    source: str
    lead_id: UUID | None
    lead_name: str | None = None
    ticket_id: UUID | None
    appointment_id: UUID | None
    call_id: UUID | None
    completed_at: datetime | None


class LeadOut(BaseModel):
    id: UUID
    name: str
    phone: str | None
    email: str | None
    company: str
    interest: str
    budget: str
    timeline: str
    score: int | None
    status: str
    source: str
    call_id: UUID | None
    created_at: datetime
    updated_at: datetime


class LeadDetail(LeadOut):
    activities: list[ActivityOut]
    follow_ups: list[FollowUpOut]


def _lead(ctx: Ctx, lead_id: UUID) -> Lead:
    lead = ctx.session.scalar(select(Lead).where(Lead.id == lead_id, Lead.tenant_id == ctx.tenant.id))
    if not lead:
        raise not_found()
    return lead


def _fu_out(f: FollowUp, lead_name: str | None = None) -> FollowUpOut:
    return FollowUpOut(
        id=f.id,
        due_at=f.due_at,
        channel=f.channel,
        note=f.note,
        status=f.status,
        source=f.source,
        lead_id=f.lead_id,
        lead_name=lead_name,
        ticket_id=f.ticket_id,
        appointment_id=f.appointment_id,
        call_id=f.call_id,
        completed_at=f.completed_at,
    )


@router.get("/v1/leads", response_model=list[LeadOut])
def list_leads(
    status_: str | None = Query(default=None, alias="status"),
    call_id: UUID | None = None,
    ctx: Ctx = Depends(require(Perm.WORKFLOWS_READ)),
) -> list[LeadOut]:
    q = select(Lead)
    if status_:
        q = q.where(Lead.status == status_)
    if call_id:
        q = q.where(Lead.call_id == call_id)
    return [
        LeadOut.model_validate(x, from_attributes=True)
        for x in ctx.session.scalars(q.order_by(Lead.created_at.desc()).limit(500))
    ]


@router.post("/v1/leads", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(data: LeadIn, ctx: Ctx = Depends(require(Perm.WORKFLOWS_MANAGE))) -> LeadOut:
    try:
        lead, _ = wf.create_lead(
            ctx.session,
            _actor(ctx),
            name=data.name,
            phone_number=data.phone,
            email=data.email,
            company=data.company,
            interest=data.interest,
            budget=data.budget,
            timeline=data.timeline,
        )
    except wf.WorkflowError as e:
        raise _fail(e) from None
    ctx.audit("lead.created", resource_type="lead", resource_id=str(lead.id))
    ctx.session.refresh(lead)
    return LeadOut.model_validate(lead, from_attributes=True)


@router.get("/v1/leads/{lead_id}", response_model=LeadDetail)
def read_lead(lead_id: UUID, ctx: Ctx = Depends(require(Perm.WORKFLOWS_READ))) -> LeadDetail:
    lead = _lead(ctx, lead_id)
    acts = ctx.session.scalars(
        select(LeadActivity).where(LeadActivity.lead_id == lead.id).order_by(LeadActivity.id.desc())
    )
    fus = ctx.session.scalars(select(FollowUp).where(FollowUp.lead_id == lead.id).order_by(FollowUp.due_at))
    return LeadDetail(
        **LeadOut.model_validate(lead, from_attributes=True).model_dump(),
        activities=[ActivityOut(kind=a.kind, body=a.body, call_id=a.call_id, created_at=a.created_at) for a in acts],
        follow_ups=[_fu_out(f) for f in fus],
    )


@router.patch("/v1/leads/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: UUID, data: LeadPatch, ctx: Ctx = Depends(require(Perm.WORKFLOWS_MANAGE))) -> LeadOut:
    lead = _lead(ctx, lead_id)
    if data.status and data.status != lead.status:
        ctx.session.add(
            LeadActivity(
                tenant_id=ctx.tenant.id,
                lead_id=lead.id,
                kind="status_change",
                body=f"Status: {lead.status} → {data.status}",
                created_by_membership_id=ctx.membership.id,
            )
        )
        lead.status = data.status
        emit(ctx.session, ctx.tenant.id, "lead.updated", {"id": str(lead.id), "status": lead.status})
    if data.owner_membership_id:
        lead.owner_membership_id = data.owner_membership_id
    ctx.session.flush()
    ctx.audit("lead.updated", resource_type="lead", resource_id=str(lead.id))
    ctx.session.refresh(lead)
    return LeadOut.model_validate(lead, from_attributes=True)


@router.post("/v1/leads/{lead_id}/notes", status_code=status.HTTP_201_CREATED)
def add_lead_note(lead_id: UUID, data: NoteIn, ctx: Ctx = Depends(require(Perm.WORKFLOWS_MANAGE))) -> dict:
    lead = _lead(ctx, lead_id)
    ctx.session.add(
        LeadActivity(
            tenant_id=ctx.tenant.id,
            lead_id=lead.id,
            kind=data.kind,
            body=data.body,
            created_by_membership_id=ctx.membership.id,
        )
    )
    return {"ok": True}


# ---------------------------------------------------------------------------------------------------- follow-ups
class FollowUpIn(BaseModel):
    due_at: datetime
    channel: Literal["call", "sms", "email", "task"] = "call"
    note: str = Field(default="", max_length=500)
    lead_id: UUID | None = None
    ticket_id: UUID | None = None
    appointment_id: UUID | None = None


class FollowUpPatch(BaseModel):
    status: Literal["open", "done", "cancelled"] | None = None
    due_at: datetime | None = None


@router.get("/v1/follow-ups", response_model=list[FollowUpOut])
def list_follow_ups(
    status_: str | None = Query(default="open", alias="status"), ctx: Ctx = Depends(require(Perm.WORKFLOWS_READ))
) -> list[FollowUpOut]:
    q = select(FollowUp, Lead.name).outerjoin(Lead, Lead.id == FollowUp.lead_id)
    if status_:
        q = q.where(FollowUp.status == status_)
    rows = ctx.session.execute(q.order_by(FollowUp.due_at).limit(500)).all()
    return [_fu_out(f, n) for f, n in rows]


@router.post("/v1/follow-ups", response_model=FollowUpOut, status_code=status.HTTP_201_CREATED)
def create_follow_up(data: FollowUpIn, ctx: Ctx = Depends(require(Perm.WORKFLOWS_MANAGE))) -> FollowUpOut:
    if data.lead_id:
        _lead(ctx, data.lead_id)
    if data.appointment_id:
        _appt(ctx, data.appointment_id)
    if data.ticket_id:
        from ..m14_support.models import Ticket

        if not ctx.session.scalar(select(Ticket.id).where(Ticket.id == data.ticket_id)):
            raise not_found()
    if data.due_at.tzinfo is None:
        raise bad_request("invalid_time", "Give the follow-up time with a time zone.")
    f = wf.add_follow_up(
        ctx.session,
        _actor(ctx),
        due_at=data.due_at,
        channel=data.channel,
        note=data.note,
        lead_id=data.lead_id,
        ticket_id=data.ticket_id,
        appointment_id=data.appointment_id,
        assignee=ctx.membership.id,
    )
    ctx.audit("follow_up.created", resource_type="follow_up", resource_id=str(f.id))
    return _fu_out(f)


@router.patch("/v1/follow-ups/{fu_id}", response_model=FollowUpOut)
def update_follow_up(
    fu_id: UUID, data: FollowUpPatch, ctx: Ctx = Depends(require(Perm.WORKFLOWS_MANAGE))
) -> FollowUpOut:
    f = ctx.session.scalar(select(FollowUp).where(FollowUp.id == fu_id, FollowUp.tenant_id == ctx.tenant.id))
    if not f:
        raise not_found()
    if data.status:
        f.status = data.status
        f.completed_at = datetime.now(UTC) if data.status == "done" else None
    if data.due_at:
        if data.due_at.tzinfo is None:
            raise bad_request("invalid_time", "Give the follow-up time with a time zone.")
        f.due_at = data.due_at
    ctx.session.flush()
    ctx.audit("follow_up.updated", resource_type="follow_up", resource_id=str(f.id), status=f.status)
    return _fu_out(f)
