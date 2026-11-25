# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""The business tools an agent can be granted (addendum G). Each tool is a fixed server-side function with a
strict input schema; the model only chooses a tool and fills its fields. Nothing here runs SQL, shell commands
or requests the model wrote, and no tool reaches an arbitrary external address.

Tools act on the native workflows (M11) and support (M14). A tool that needs an outside system (an order system
for lookup_order, an SMS provider for delivery) says so instead of pretending."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..m05_agents.schemas import AgentConfig
from ..m11_workflows import service as wf
from ..m11_workflows.models import Appointment, BookingCalendar
from ..m14_support import service as support
from ..m14_support.models import NotificationTemplate


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CheckAvailabilityIn(Strict):
    date: str | None = Field(default=None, description="Day to check, YYYY-MM-DD. Leave out for the next free day.")


class BookIn(Strict):
    start: str = Field(description="Exact slot start from check_availability, YYYY-MM-DDTHH:MM, local time.")
    name: str = Field(min_length=1, max_length=120, description="The caller's name.")
    phone: str | None = Field(default=None, max_length=30, description="The caller's phone number, if given.")
    notes: str = Field(default="", max_length=500, description="What the appointment is for, briefly.")


class RescheduleIn(Strict):
    reference: str = Field(min_length=3, max_length=20, description="Booking reference, like A-7K3M9Q.")
    phone: str | None = Field(default=None, max_length=30, description="Phone number the booking was made with.")
    new_start: str = Field(description="New slot start from check_availability, YYYY-MM-DDTHH:MM.")


class CancelIn(Strict):
    reference: str = Field(min_length=3, max_length=20, description="Booking reference, like A-7K3M9Q.")
    phone: str | None = Field(default=None, max_length=30, description="Phone number the booking was made with.")
    reason: str = Field(default="", max_length=300)


class LeadIn(Strict):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=200)
    company: str = Field(default="", max_length=120)
    interest: str = Field(default="", max_length=1000, description="What they need, in their words.")
    budget: str = Field(default="", max_length=120)
    timeline: str = Field(default="", max_length=120, description="When they want it.")
    wants_callback: bool = Field(default=False, description="True if they asked to be called back.")
    callback_time: str | None = Field(default=None, description="When to call back, YYYY-MM-DDTHH:MM local time.")


class TicketIn(Strict):
    subject: str = Field(min_length=3, max_length=200, description="One-line summary of the problem.")
    description: str = Field(default="", max_length=2000, description="Details the caller gave.")
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    name: str = Field(default="", max_length=120)
    phone: str | None = Field(default=None, max_length=30)


class OrderIn(Strict):
    order_reference: str = Field(min_length=2, max_length=40)


class SmsIn(Strict):
    reference: str = Field(min_length=3, max_length=20, description="Booking reference to confirm by SMS.")


@dataclass
class ToolContext:
    actor: wf.Actor
    cfg: AgentConfig
    business_name: str
    idempotency_key: str


Handler = Callable[[Session, ToolContext, Any], dict[str, Any]]


@dataclass(frozen=True)
class ToolDef:
    key: str
    label: str
    description: str  # for the model
    schema: type[Strict]
    handler: Handler
    module: str
    sensitive_default: bool = False  # needs a person's approval unless the tenant turns that off


def _calendar(s: Session, cfg: AgentConfig) -> BookingCalendar:
    cal = s.get(BookingCalendar, cfg.booking_calendar_id) if cfg.booking_calendar_id else None
    if not cal or cal.status != "active":
        raise wf.WorkflowError("no_calendar", "Online booking isn't set up for this agent.")
    return cal


def _check(s: Session, c: ToolContext, a: CheckAvailabilityIn) -> dict[str, Any]:
    day = None
    if a.date:
        try:
            day = date.fromisoformat(a.date)
        except ValueError:
            raise wf.WorkflowError("invalid_date", "Dates must look like 2026-11-26.") from None
    return wf.availability(s, _calendar(s, c.cfg), day)


def _book(s: Session, c: ToolContext, a: BookIn) -> dict[str, Any]:
    cal = _calendar(s, c.cfg)
    appt = wf.book(s, c.actor, cal.id, start=a.start, name=a.name, phone_number=a.phone, notes=a.notes)
    return {"booked": True, **wf.appointment_payload(appt, cal)}


def _reschedule(s: Session, c: ToolContext, a: RescheduleIn) -> dict[str, Any]:
    appt = wf.find_appointment(s, a.reference, a.phone, c.actor.country)
    appt = wf.reschedule(s, c.actor, appt, a.new_start)
    cal = s.get(BookingCalendar, appt.calendar_id)
    assert cal is not None
    return {"rescheduled": True, **wf.appointment_payload(appt, cal)}


def _cancel(s: Session, c: ToolContext, a: CancelIn) -> dict[str, Any]:
    appt = wf.find_appointment(s, a.reference, a.phone, c.actor.country)
    appt = wf.cancel(s, c.actor, appt, a.reason)
    return {"cancelled": True, "reference": appt.reference}


def _lead(s: Session, c: ToolContext, a: LeadIn) -> dict[str, Any]:
    when = None
    if a.callback_time:
        tz = ZoneInfo(c.cfg.business_hours.timezone)
        try:
            when = datetime.fromisoformat(a.callback_time)
        except ValueError:
            raise wf.WorkflowError("invalid_time", "Times must look like 2026-11-26T10:30.") from None
        when = when if when.tzinfo else when.replace(tzinfo=tz)
    elif a.wants_callback:
        when = datetime.now(UTC) + timedelta(hours=1)
    lead, fu = wf.create_lead(
        s,
        c.actor,
        name=a.name,
        phone_number=a.phone,
        email=a.email,
        company=a.company,
        interest=a.interest,
        budget=a.budget,
        timeline=a.timeline,
        callback_at=when,
    )
    return {"lead_created": True, "qualification_score": lead.score, "callback_scheduled": fu is not None}


def _ticket(s: Session, c: ToolContext, a: TicketIn) -> dict[str, Any]:
    t = support.create_ticket(
        s, c.actor, subject=a.subject, description=a.description, priority=a.priority, name=a.name, phone_number=a.phone
    )
    return {"ticket_created": True, "reference": t.reference, "priority": t.priority}


def _order(s: Session, c: ToolContext, a: OrderIn) -> dict[str, Any]:
    raise wf.WorkflowError(
        "not_connected",
        "Order lookups need an order system connected under Integrations (awaiting configuration). "
        "Offer to take a message instead.",
    )


def _sms(s: Session, c: ToolContext, a: SmsIn) -> dict[str, Any]:
    appt = s.scalar(select(Appointment).where(Appointment.reference == a.reference.strip().upper()))
    if not appt or appt.call_id != c.actor.call_id:
        raise wf.WorkflowError("not_found", "I can only confirm a booking made on this call.")
    if not appt.customer_phone:
        raise wf.WorkflowError("no_recipient", "The booking has no phone number to send to.")
    cal = s.get(BookingCalendar, appt.calendar_id)
    assert cal is not None
    local = appt.starts_at.astimezone(ZoneInfo(cal.timezone))
    n = support.send(
        s,
        c.actor,
        key="appointment_confirmation",
        channel="sms",
        recipient=appt.customer_phone,
        values={
            "customer_name": appt.customer_name,
            "reference": appt.reference,
            "date_time": wf.say_time(local),
            "business_name": c.business_name,
        },
        idempotency_key=f"sms-confirm:{appt.id}",
        related_type="appointment",
        related_id=appt.id,
    )
    sent = n.status in ("queued", "sent")
    return {
        "message_queued": sent,
        "note": None
        if sent
        else "The confirmation is saved but can't be sent yet; tell the caller staff will confirm.",
    }


TOOLS: dict[str, ToolDef] = {
    t.key: t
    for t in (
        ToolDef(
            "check_availability",
            "Check appointment availability",
            "List free appointment times on a day. Always call this before booking or rescheduling.",
            CheckAvailabilityIn,
            _check,
            "M11",
        ),
        ToolDef(
            "book_appointment",
            "Book an appointment",
            "Book a free slot returned by check_availability. Confirm the time and name with the caller first.",
            BookIn,
            _book,
            "M11",
        ),
        ToolDef(
            "reschedule_appointment",
            "Reschedule an appointment",
            "Move an existing booking to another free slot. Needs the booking reference.",
            RescheduleIn,
            _reschedule,
            "M11",
        ),
        ToolDef(
            "cancel_appointment",
            "Cancel an appointment",
            "Cancel an existing booking. Needs the booking reference. Confirm with the caller first.",
            CancelIn,
            _cancel,
            "M11",
            sensitive_default=True,
        ),
        ToolDef(
            "create_lead",
            "Capture a lead",
            "Save an interested caller as a sales lead, with what they need, budget and timeline if they said.",
            LeadIn,
            _lead,
            "M11",
        ),
        ToolDef(
            "create_ticket",
            "Create a support ticket",
            "Open a support ticket for a problem the caller reports that you can't solve on the call.",
            TicketIn,
            _ticket,
            "M14",
        ),
        ToolDef(
            "lookup_order",
            "Look up an order",
            "Look up the status of the caller's order by its reference.",
            OrderIn,
            _order,
            "M13",
        ),
        ToolDef(
            "send_sms_confirmation",
            "Send an SMS confirmation",
            "Send the approved SMS confirmation for a booking made on this call.",
            SmsIn,
            _sms,
            "M14",
        ),
    )
}


def json_schema(t: ToolDef) -> dict[str, Any]:
    """The tool's input schema for the model, without pydantic's titles."""

    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return strip(t.schema.model_json_schema())


def unavailable(s: Session, key: str, cfg: AgentConfig) -> str | None:
    """Why a granted tool can't run for this agent now, or None. Shown in readiness and enforced at run time."""
    if key in ("check_availability", "book_appointment", "reschedule_appointment", "cancel_appointment"):
        cal = s.get(BookingCalendar, cfg.booking_calendar_id) if cfg.booking_calendar_id else None
        if not cal or cal.status != "active":
            return "Choose an active booking calendar for this agent."
    if key == "lookup_order":
        return "Needs an order system connected under Integrations (awaiting configuration)."
    if key == "send_sms_confirmation":
        ok = s.scalar(
            select(NotificationTemplate.id).where(
                NotificationTemplate.key == "appointment_confirmation",
                NotificationTemplate.channel == "sms",
                NotificationTemplate.status == "approved",
            )
        )
        if not ok:
            return "Needs an approved SMS message called appointment_confirmation under Notifications."
    return None


def known(key: str) -> bool:
    return key in TOOLS
