# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Outbound campaigns API (M07). No unrestricted bulk calling (addendum I): a campaign is a draft until someone
with approve rights approves it (another person when the organisation has one), any edit sends it back to draft,
and every contact is still checked by the policy engine (consent, do-not-call, window, caps) before each call."""

from datetime import UTC, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from ...core.context import Ctx, require
from ...core.errors import bad_request, conflict, forbidden, not_found
from ...core.permissions import Perm, has
from ..m02_tenant.models import Membership
from ..m04_telephony import service as tel
from ..m04_telephony.models import PhoneNumber, SipTrunk
from ..m05_agents.models import Agent
from ..m05_agents.router import production_version
from ..m08_calls.models import Call
from ..m22_consent import service as consent
from ..m22_consent.router import Basis
from .models import Campaign, CampaignContact, DialAttempt, PolicyDecision
from .policy import DAY_KEYS

router = APIRouter(tags=["campaigns"])
EDITABLE = ("draft", "approved", "paused")
MAX_IMPORT = 1000


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(default="", max_length=500)
    agent_id: UUID
    from_number_id: UUID
    timezone: str = Field(min_length=1, max_length=60)
    window_start: time = time(10, 0)
    window_end: time = time(18, 0)
    days: list[str] = Field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri"], min_length=1, max_length=7)
    max_attempts: int = Field(default=2, ge=1, le=5)
    retry_minutes: int = Field(default=120, ge=15, le=10080)
    max_concurrent: int = Field(default=1, ge=1, le=10)
    calls_per_minute: int = Field(default=2, ge=1, le=30)

    @field_validator("days")
    @classmethod
    def _days(cls, v: list[str]) -> list[str]:
        days = [d.lower() for d in v]
        if any(d not in DAY_KEYS for d in days):
            raise ValueError("days must be mon..sun")
        return sorted(set(days), key=DAY_KEYS.index)


class CampaignOut(CampaignIn):
    id: UUID
    status: str
    agent_name: str
    from_number: str
    approved_by_membership_id: UUID | None
    approved_at: datetime | None
    created_by_membership_id: UUID | None
    created_at: datetime
    updated_at: datetime
    counts: dict[str, int]


class ContactIn(BaseModel):
    phone: str = Field(min_length=1, max_length=30)  # bad numbers are reported per row, not refused as a whole
    name: str = Field(default="", max_length=120)
    timezone: str | None = Field(default=None, max_length=60)


class ImportIn(BaseModel):
    contacts: list[ContactIn] = Field(min_length=1, max_length=MAX_IMPORT)
    # Record consent for every imported contact (the organisation states it holds it, and how).
    consent_basis: Basis | None = None
    consent_evidence: str = Field(default="", max_length=1000)


class ImportOut(BaseModel):
    added: int
    duplicates: int
    invalid: list[dict]
    consent_recorded: int
    on_do_not_call_list: int


class ContactOut(BaseModel):
    id: UUID
    phone: str
    name: str
    timezone: str | None
    status: str
    attempts: int
    next_attempt_at: datetime
    last_outcome: str | None
    last_call_id: UUID | None
    block_reason: str | None
    updated_at: datetime


class DecisionOut(BaseModel):
    id: int
    contact_id: UUID | None
    call_id: UUID | None
    phone: str
    decision: str
    reason: str | None
    checks: list
    created_at: datetime


class AttemptOut(BaseModel):
    contact_id: UUID
    call_id: UUID
    attempt_no: int
    outcome: str | None
    sip_status: int | None
    started_at: datetime
    ended_at: datetime | None


def _campaign(ctx: Ctx, campaign_id: UUID, *, lock: bool = False) -> Campaign:
    q = select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == ctx.tenant.id)
    c = ctx.session.scalar(q.with_for_update() if lock else q)
    if not c:
        raise not_found()
    return c


def _out(ctx: Ctx, c: Campaign) -> CampaignOut:
    a = ctx.session.get(Agent, c.agent_id)
    n = ctx.session.get(PhoneNumber, c.from_number_id)
    counts = dict(
        ctx.session.execute(
            select(CampaignContact.status, func.count())
            .where(CampaignContact.campaign_id == c.id)
            .group_by(CampaignContact.status)
        ).all()
    )
    return CampaignOut(
        id=c.id,
        name=c.name,
        purpose=c.purpose,
        agent_id=c.agent_id,
        from_number_id=c.from_number_id,
        timezone=c.timezone,
        window_start=c.window_start,
        window_end=c.window_end,
        days=list(c.days),
        max_attempts=c.max_attempts,
        retry_minutes=c.retry_minutes,
        max_concurrent=c.max_concurrent,
        calls_per_minute=c.calls_per_minute,
        status=c.status,
        agent_name=a.name if a else "",
        from_number=n.e164 if n else "",
        approved_by_membership_id=c.approved_by_membership_id,
        approved_at=c.approved_at,
        created_by_membership_id=c.created_by_membership_id,
        created_at=c.created_at,
        updated_at=c.updated_at,
        counts={k: int(v) for k, v in counts.items()},
    )


def _validate(ctx: Ctx, data: CampaignIn) -> None:
    try:
        ZoneInfo(data.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise bad_request("invalid_timezone", "Choose a time zone such as Asia/Kolkata.") from None
    if data.window_start >= data.window_end:
        raise bad_request("invalid_window", "The calling window must start before it ends.")
    agent = ctx.session.scalar(select(Agent).where(Agent.id == data.agent_id, Agent.tenant_id == ctx.tenant.id))
    if not agent or agent.status == "archived":
        raise bad_request("agent_not_found", "Choose one of your agents.")
    n = ctx.session.scalar(
        select(PhoneNumber).where(PhoneNumber.id == data.from_number_id, PhoneNumber.tenant_id == ctx.tenant.id)
    )
    if not n or n.status != "active" or not n.outbound:
        raise bad_request("number_not_outbound", "Choose one of your active numbers that can place calls.")
    t = ctx.session.get(SipTrunk, n.trunk_id)
    if not t or t.direction == "inbound":
        raise bad_request("number_not_outbound", "That number's trunk only receives calls.")


def _apply(c: Campaign, data: CampaignIn) -> None:
    for k, v in data.model_dump().items():
        setattr(c, k, v.strip() if isinstance(v, str) and k in ("name", "purpose") else v)


@router.get("/v1/campaigns", response_model=list[CampaignOut])
def list_campaigns(ctx: Ctx = Depends(require(Perm.CAMPAIGNS_READ))) -> list[CampaignOut]:
    return [_out(ctx, c) for c in ctx.session.scalars(select(Campaign).order_by(Campaign.created_at.desc()))]


@router.post("/v1/campaigns", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def create_campaign(data: CampaignIn, ctx: Ctx = Depends(require(Perm.CAMPAIGNS_MANAGE))) -> CampaignOut:
    _validate(ctx, data)
    c = Campaign(tenant_id=ctx.tenant.id, created_by_membership_id=ctx.membership.id, status="draft")
    _apply(c, data)
    ctx.session.add(c)
    ctx.session.flush()
    ctx.session.refresh(c)
    ctx.audit("campaign.created", resource_type="campaign", resource_id=str(c.id))
    return _out(ctx, c)


@router.get("/v1/campaigns/{campaign_id}", response_model=CampaignOut)
def read_campaign(campaign_id: UUID, ctx: Ctx = Depends(require(Perm.CAMPAIGNS_READ))) -> CampaignOut:
    return _out(ctx, _campaign(ctx, campaign_id))


@router.put("/v1/campaigns/{campaign_id}", response_model=CampaignOut)
def update_campaign(
    campaign_id: UUID, data: CampaignIn, ctx: Ctx = Depends(require(Perm.CAMPAIGNS_MANAGE))
) -> CampaignOut:
    c = _campaign(ctx, campaign_id, lock=True)
    if c.status not in EDITABLE:
        raise conflict("campaign_locked", "Pause the campaign before you change it.")
    _validate(ctx, data)
    _apply(c, data)
    was = c.status
    c.status, c.approved_by_membership_id, c.approved_at = "draft", None, None  # any edit needs a new approval
    c.updated_at = datetime.now(UTC)
    ctx.audit("campaign.updated", resource_type="campaign", resource_id=str(c.id), previous_status=was)
    return _out(ctx, c)


def _other_approvers(ctx: Ctx) -> bool:
    roles = ctx.session.scalars(
        select(Membership.role).where(
            Membership.tenant_id == ctx.tenant.id, Membership.status == "active", Membership.id != ctx.membership.id
        )
    )
    return any(has(r, Perm.CAMPAIGNS_APPROVE) for r in roles)


@router.post("/v1/campaigns/{campaign_id}/approve", response_model=CampaignOut)
def approve_campaign(campaign_id: UUID, ctx: Ctx = Depends(require(Perm.CAMPAIGNS_APPROVE))) -> CampaignOut:
    c = _campaign(ctx, campaign_id, lock=True)
    if c.status != "draft":
        raise conflict("not_draft", "Only a draft campaign can be approved.")
    self_approval = c.created_by_membership_id == ctx.membership.id
    if self_approval and _other_approvers(ctx):
        raise forbidden("Another person with approve rights must approve a campaign you created.")
    if not ctx.session.scalar(select(CampaignContact.id).where(CampaignContact.campaign_id == c.id).limit(1)):
        raise bad_request("no_contacts", "Add contacts before approving the campaign.")
    c.status, c.approved_by_membership_id = "approved", ctx.membership.id
    c.approved_at = c.updated_at = datetime.now(UTC)
    ctx.audit("campaign.approved", resource_type="campaign", resource_id=str(c.id), self_approved=self_approval)
    return _out(ctx, c)


@router.post("/v1/campaigns/{campaign_id}/start", response_model=CampaignOut)
def start_campaign(campaign_id: UUID, ctx: Ctx = Depends(require(Perm.CAMPAIGNS_MANAGE))) -> CampaignOut:
    c = _campaign(ctx, campaign_id, lock=True)
    if c.status not in ("approved", "paused"):
        raise conflict("not_approved", "Only an approved or paused campaign can start.")
    if c.approved_at is None:
        raise conflict("not_approved", "This campaign needs approval first.")
    agent = ctx.session.get(Agent, c.agent_id)
    if not agent or production_version(ctx.session, agent) is None:
        raise bad_request("agent_not_published", "Publish the campaign's agent before starting it.")
    pol = tel.policy_for(ctx.session, ctx.tenant.id, ctx.tenant.country_code)
    if not pol.telephony_enabled:
        raise conflict("telephony_paused", "Your organisation has paused phone calls.")
    c.status, c.updated_at = "running", datetime.now(UTC)
    ctx.audit("campaign.started", resource_type="campaign", resource_id=str(c.id))
    return _out(ctx, c)


@router.post("/v1/campaigns/{campaign_id}/pause", response_model=CampaignOut)
def pause_campaign(campaign_id: UUID, ctx: Ctx = Depends(require(Perm.CAMPAIGNS_MANAGE))) -> CampaignOut:
    """Stops new calls at once. Calls already in progress finish normally."""
    c = _campaign(ctx, campaign_id, lock=True)
    if c.status != "running":
        raise conflict("not_running", "Only a running campaign can be paused.")
    c.status, c.updated_at = "paused", datetime.now(UTC)
    ctx.audit("campaign.paused", resource_type="campaign", resource_id=str(c.id))
    return _out(ctx, c)


@router.post("/v1/campaigns/{campaign_id}/cancel", response_model=CampaignOut)
def cancel_campaign(campaign_id: UUID, ctx: Ctx = Depends(require(Perm.CAMPAIGNS_MANAGE))) -> CampaignOut:
    c = _campaign(ctx, campaign_id, lock=True)
    if c.status in ("completed", "cancelled"):
        raise conflict("campaign_ended", "This campaign has already ended.")
    now = datetime.now(UTC)
    c.status, c.updated_at = "cancelled", now
    for k in ctx.session.scalars(
        select(CampaignContact).where(
            CampaignContact.campaign_id == c.id, CampaignContact.status.in_(("pending", "retry"))
        )
    ):
        k.status, k.updated_at = "cancelled", now
    ctx.audit("campaign.cancelled", resource_type="campaign", resource_id=str(c.id))
    return _out(ctx, c)


# ---------------------------------------------------------------------------------------------------- contacts
@router.get("/v1/campaigns/{campaign_id}/contacts", response_model=list[ContactOut])
def list_contacts(
    campaign_id: UUID,
    status_: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    ctx: Ctx = Depends(require(Perm.CAMPAIGNS_READ)),
) -> list[ContactOut]:
    c = _campaign(ctx, campaign_id)
    q = select(CampaignContact).where(CampaignContact.campaign_id == c.id)
    if status_:
        q = q.where(CampaignContact.status == status_)
    rows = ctx.session.scalars(q.order_by(CampaignContact.created_at, CampaignContact.phone).limit(limit))
    return [ContactOut.model_validate(k, from_attributes=True) for k in rows]


@router.post("/v1/campaigns/{campaign_id}/contacts", response_model=ImportOut)
def import_contacts(campaign_id: UUID, data: ImportIn, ctx: Ctx = Depends(require(Perm.CAMPAIGNS_MANAGE))) -> ImportOut:
    """Adds contacts. Numbers are normalised to E.164; invalid ones are reported, never dialled. Recording consent
    here needs consent rights too, and is itself audited."""
    c = _campaign(ctx, campaign_id, lock=True)
    if c.status not in ("draft", "paused"):
        raise conflict("campaign_locked", "Add contacts to a draft or paused campaign.")
    if data.consent_basis:
        ctx.require(Perm.CONSENT_MANAGE)
    existing = set(ctx.session.scalars(select(CampaignContact.phone).where(CampaignContact.campaign_id == c.id)))
    added = dup = consented = listed = 0
    invalid: list[dict] = []
    for i, row in enumerate(data.contacts):
        try:
            phone, _ = tel.e164(row.phone, ctx.tenant.country_code)
        except tel.TelephonyError:
            invalid.append({"row": i + 1, "phone": row.phone[:30], "reason": "invalid_phone"})
            continue
        tz = (row.timezone or "").strip() or None
        if tz:
            try:
                ZoneInfo(tz)
            except (ZoneInfoNotFoundError, ValueError):
                invalid.append({"row": i + 1, "phone": phone, "reason": "invalid_timezone"})
                continue
        if phone in existing:
            dup += 1
            continue
        existing.add(phone)
        ctx.session.add(
            CampaignContact(tenant_id=ctx.tenant.id, campaign_id=c.id, phone=phone, name=row.name.strip(), timezone=tz)
        )
        added += 1
        suppressed = consent.is_suppressed(ctx.session, phone)
        listed += int(suppressed)
        if data.consent_basis and not suppressed and not consent.has_consent(ctx.session, phone, "outbound_calls"):
            consent.record_consent(
                ctx.session,
                tenant_id=ctx.tenant.id,
                phone=phone,
                purpose="outbound_calls",
                status="granted",
                basis=data.consent_basis,
                source="import",
                evidence=data.consent_evidence,
                membership_id=ctx.membership.id,
            )
            consented += 1
    if added and c.status != "draft":
        c.status, c.approved_by_membership_id, c.approved_at = "draft", None, None  # new contacts: approve again
    c.updated_at = datetime.now(UTC)
    ctx.session.flush()
    ctx.audit(
        "campaign.contacts_imported",
        resource_type="campaign",
        resource_id=str(c.id),
        added=added,
        duplicates=dup,
        invalid=len(invalid),
        consent_recorded=consented,
        consent_basis=data.consent_basis,
    )
    return ImportOut(
        added=added, duplicates=dup, invalid=invalid, consent_recorded=consented, on_do_not_call_list=listed
    )


@router.delete("/v1/campaigns/{campaign_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_contact(campaign_id: UUID, contact_id: UUID, ctx: Ctx = Depends(require(Perm.CAMPAIGNS_MANAGE))) -> None:
    c = _campaign(ctx, campaign_id)
    k = ctx.session.scalar(
        select(CampaignContact).where(CampaignContact.id == contact_id, CampaignContact.campaign_id == c.id)
    )
    if not k:
        raise not_found()
    if k.attempts or k.status not in ("pending", "blocked"):
        k.status, k.updated_at = "cancelled", datetime.now(UTC)  # called before: kept for the history
    else:
        ctx.session.delete(k)
    ctx.audit("campaign.contact_removed", resource_type="campaign", resource_id=str(c.id))


@router.get("/v1/campaigns/{campaign_id}/decisions", response_model=list[DecisionOut])
def list_decisions(
    campaign_id: UUID,
    contact_id: UUID | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    ctx: Ctx = Depends(require(Perm.CAMPAIGNS_READ)),
) -> list[DecisionOut]:
    c = _campaign(ctx, campaign_id)
    q = select(PolicyDecision).where(PolicyDecision.campaign_id == c.id)
    if contact_id:
        q = q.where(PolicyDecision.contact_id == contact_id)
    rows = ctx.session.scalars(q.order_by(PolicyDecision.id.desc()).limit(limit))
    return [DecisionOut.model_validate(d, from_attributes=True) for d in rows]


@router.get("/v1/campaigns/{campaign_id}/attempts", response_model=list[AttemptOut])
def list_attempts(campaign_id: UUID, ctx: Ctx = Depends(require(Perm.CAMPAIGNS_READ))) -> list[AttemptOut]:
    c = _campaign(ctx, campaign_id)
    rows = ctx.session.scalars(
        select(DialAttempt).where(DialAttempt.campaign_id == c.id).order_by(DialAttempt.id.desc()).limit(500)
    )
    return [AttemptOut.model_validate(a, from_attributes=True) for a in rows]


@router.get("/v1/campaigns/{campaign_id}/live")
def live(campaign_id: UUID, ctx: Ctx = Depends(require(Perm.CAMPAIGNS_READ))) -> dict:
    from ..m08_calls import lifecycle

    c = _campaign(ctx, campaign_id)
    n = ctx.session.scalar(
        select(func.count())
        .select_from(Call)
        .where(Call.campaign_id == c.id, Call.state.not_in(lifecycle.TERMINAL_STATES))
    )
    return {"live_calls": n or 0}
