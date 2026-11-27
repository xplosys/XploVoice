# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Super Admin billing (M17 with M15, Phase 7): plans and price lists, FX and tax rates, every organisation's
subscription, credits, voiding invoices, running the billing job, and the commercial overview with provider cost
next to tenant charges.

Same rules as the rest of /admin/v1: platform-admin flag, an MFA session, a written reason for every change, and
every call audited on the platform chain. Writes to an organisation's data switch to that organisation's RLS
context for the one statement, so its tenant policy still applies."""

import contextlib
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from ...core import audit
from ...core.context import Ctx
from ...core.errors import bad_request, conflict, not_found
from ..m17_admin.router import platform_admin
from . import billing
from .billing_router import InvoiceDetail, PlanOut, invoice_detail, plan_out

router = APIRouter(prefix="/admin/v1/billing", tags=["M17 Super Admin billing"])

Meter = Literal[
    "base_fee",
    "phone_inbound_minute",
    "phone_outbound_minute",
    "llm_input_1k_tokens",
    "llm_output_1k_tokens",
    "stt_minute",
    "tts_1k_characters",
]


def _log(ctx: Ctx, action: str, rtype: str, rid: str | None, reason: str | None = None, **meta: Any) -> None:
    audit.record(
        ctx.session,
        action=action,
        result="success",
        tenant_id=None,
        actor_user_id=ctx.user.id,
        actor_kind="platform_admin",
        resource_type=rtype,
        resource_id=rid,
        reason=reason,
        ip_hash=ctx.meta.ip_hash,
        correlation_id=ctx.meta.correlation_id,
        metadata=meta,
    )


@contextlib.contextmanager
def as_tenant(ctx: Ctx, tenant_id: UUID) -> Iterator[None]:
    ctx.session.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
    try:
        yield
    finally:
        ctx.session.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(ctx.tenant.id)})


def _tenant(ctx: Ctx, tenant_id: UUID) -> Any:
    t = ctx.session.execute(
        text("select id, name, currency, country_code from tenants where id = :i"), {"i": tenant_id}
    ).first()
    if t is None:
        raise not_found("Tenant not found")
    return t


# ------------------------------------------------------------------ plans
class PriceIn(BaseModel):
    meter: Meter
    unit_price: Decimal = Field(ge=0, max_digits=24, decimal_places=12)
    included_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=20, decimal_places=6)
    monthly_cap: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=6)


class Limits(BaseModel):
    max_agents: int | None = Field(default=None, ge=1, le=10000)
    max_concurrent_calls: int | None = Field(default=None, ge=1, le=1000)
    max_phone_numbers: int | None = Field(default=None, ge=0, le=10000)


class PlanIn(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,39}$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=1000)
    kind: Literal["subscription", "payg"]
    currency: Literal["INR", "USD"]
    trial_days: int = Field(default=0, ge=0, le=90)
    limits: Limits = Limits()
    prices: list[PriceIn] = Field(default_factory=list, max_length=7)
    reason: str = Field(min_length=5, max_length=500)


class AdminPlanOut(PlanOut):
    subscribers: int


def _admin_plan(ctx: Ctx, plan: Any) -> AdminPlanOut:
    n = ctx.session.scalar(
        text("select count(*) from subscriptions where plan_id = :p and ended_at is null"), {"p": plan["id"]}
    )
    return AdminPlanOut(**plan_out(ctx.session, plan).model_dump(), subscribers=n or 0)


def _get_plan(ctx: Ctx, plan_id: UUID) -> Any:
    p = ctx.session.execute(text("select * from billing_plans where id = :i"), {"i": plan_id}).mappings().first()
    if p is None:
        raise not_found("Plan not found")
    return p


def _add_price(ctx: Ctx, plan: Any, p: PriceIn) -> None:
    if plan["kind"] == "payg" and p.meter == "base_fee" and p.unit_price > 0:
        raise bad_request("payg_fee", "A pay-as-you-go plan has no plan fee.")
    if p.meter == "base_fee" and (p.included_quantity or p.monthly_cap):
        raise bad_request("fee_quantities", "The plan fee has no included quantity or quota.")
    ctx.session.execute(
        text(
            "insert into plan_prices (plan_id, meter, unit_price, included_quantity, monthly_cap, created_by) "
            "values (:p, :m, :u, :i, :c, :by)"
        ),
        {
            "p": plan["id"],
            "m": p.meter,
            "u": p.unit_price,
            "i": p.included_quantity,
            "c": p.monthly_cap,
            "by": ctx.user.id,
        },
    )


@router.get("/plans", response_model=list[AdminPlanOut])
def list_plans(ctx: Ctx = Depends(platform_admin)) -> list[AdminPlanOut]:
    rows = ctx.session.execute(text("select * from billing_plans order by status, currency, name")).mappings().all()
    _log(ctx, "admin.plans_listed", "billing_plan", None)
    return [_admin_plan(ctx, r) for r in rows]


@router.post("/plans", response_model=AdminPlanOut, status_code=201)
def create_plan(data: PlanIn, ctx: Ctx = Depends(platform_admin)) -> AdminPlanOut:
    if ctx.session.scalar(text("select 1 from billing_plans where code = :c"), {"c": data.code}):
        raise conflict("code_taken", "A plan with this code exists.")
    if len({p.meter for p in data.prices}) != len(data.prices):
        raise bad_request("duplicate_meter", "Each meter can have one price.")
    pid = ctx.session.scalar(
        text(
            "insert into billing_plans (code, name, description, kind, currency, trial_days, limits, created_by) "
            "values (:code, :name, :d, :k, :c, :t, cast(:l as jsonb), :by) returning id"
        ),
        {
            "code": data.code,
            "name": data.name,
            "d": data.description,
            "k": data.kind,
            "c": data.currency,
            "t": data.trial_days,
            "l": data.limits.model_dump_json(exclude_none=True),
            "by": ctx.user.id,
        },
    )
    plan = _get_plan(ctx, pid)
    for p in data.prices:
        _add_price(ctx, plan, p)
    _log(ctx, "admin.plan_created", "billing_plan", str(pid), data.reason, code=data.code, currency=data.currency)
    return _admin_plan(ctx, plan)


class NewPriceIn(PriceIn):
    reason: str = Field(min_length=5, max_length=500)


@router.post("/plans/{plan_id}/prices", response_model=AdminPlanOut)
def add_price(plan_id: UUID, data: NewPriceIn, ctx: Ctx = Depends(platform_admin)) -> AdminPlanOut:
    """A price change is a new row in force from now; earlier usage keeps the price it was rated at."""
    plan = _get_plan(ctx, plan_id)
    if plan["status"] == "retired":
        raise conflict("retired", "A retired plan cannot be changed.")
    _add_price(ctx, plan, data)
    _log(
        ctx,
        "admin.plan_price_added",
        "billing_plan",
        str(plan_id),
        data.reason,
        meter=data.meter,
        unit_price=str(data.unit_price),
    )
    return _admin_plan(ctx, plan)


class PlanStatusIn(BaseModel):
    status: Literal["active", "retired"]
    is_default: bool = False
    reason: str = Field(min_length=5, max_length=500)


@router.post("/plans/{plan_id}/status", response_model=AdminPlanOut)
def plan_status(plan_id: UUID, data: PlanStatusIn, ctx: Ctx = Depends(platform_admin)) -> AdminPlanOut:
    plan = _get_plan(ctx, plan_id)
    if plan["status"] == "retired":
        raise conflict("retired", "A retired plan stays retired.")
    if (
        data.status == "active"
        and plan["kind"] == "subscription"
        and "base_fee" not in billing.prices(ctx.session, plan_id)
    ):
        raise bad_request("no_fee", "Set the plan fee before activating a subscription plan.")
    if data.is_default and data.status == "active":
        ctx.session.execute(
            text("update billing_plans set is_default = false, updated_at = now() where currency = :c and is_default"),
            {"c": plan["currency"]},
        )
    ctx.session.execute(
        text("update billing_plans set status = :s, is_default = :d, updated_at = now() where id = :i"),
        {"s": data.status, "d": data.is_default and data.status == "active", "i": plan_id},
    )
    _log(ctx, f"admin.plan_{data.status}", "billing_plan", str(plan_id), data.reason, is_default=data.is_default)
    return _admin_plan(ctx, _get_plan(ctx, plan_id))


# ------------------------------------------------------------------ FX and tax
class FxIn(BaseModel):
    base: Literal["INR", "USD"]
    quote: Literal["INR", "USD"]
    rate: Decimal = Field(gt=0, max_digits=24, decimal_places=12)
    source: str = Field(min_length=3, max_length=200)
    reason: str = Field(min_length=5, max_length=500)


class FxOut(BaseModel):
    base: str
    quote: str
    rate: Decimal
    source: str
    effective_from: datetime


@router.get("/fx-rates", response_model=list[FxOut])
def fx_rates(ctx: Ctx = Depends(platform_admin)) -> list[FxOut]:
    rows = ctx.session.execute(text("select * from fx_rates order by effective_from desc limit 100")).mappings().all()
    return [FxOut(**{k: r[k] for k in FxOut.model_fields}) for r in rows]


@router.post("/fx-rates", response_model=FxOut, status_code=201)
def add_fx(data: FxIn, ctx: Ctx = Depends(platform_admin)) -> FxOut:
    if data.base == data.quote:
        raise bad_request("same_currency", "Choose two different currencies.")
    r = (
        ctx.session.execute(
            text(
                "insert into fx_rates (base, quote, rate, source, created_by) values (:b, :q, :r, :s, :by) returning *"
            ),
            {"b": data.base, "q": data.quote, "r": data.rate, "s": data.source, "by": ctx.user.id},
        )
        .mappings()
        .one()
    )
    _log(ctx, "admin.fx_rate_added", "fx_rate", f"{data.base}/{data.quote}", data.reason, rate=str(data.rate))
    return FxOut(**{k: r[k] for k in FxOut.model_fields})


class TaxIn(BaseModel):
    country_code: Literal["IN", "US"]
    label: str = Field(min_length=2, max_length=60)
    rate_percent: Decimal = Field(ge=0, le=50, max_digits=6, decimal_places=3)
    source: str = Field(min_length=3, max_length=200)
    reason: str = Field(min_length=5, max_length=500)


class TaxOut(BaseModel):
    country_code: str
    label: str
    rate_percent: Decimal
    source: str
    effective_from: datetime


@router.get("/tax-rates", response_model=list[TaxOut])
def tax_rates(ctx: Ctx = Depends(platform_admin)) -> list[TaxOut]:
    rows = ctx.session.execute(text("select * from tax_rates order by effective_from desc limit 100")).mappings().all()
    return [TaxOut(**{k: r[k] for k in TaxOut.model_fields}) for r in rows]


@router.post("/tax-rates", response_model=TaxOut, status_code=201)
def add_tax(data: TaxIn, ctx: Ctx = Depends(platform_admin)) -> TaxOut:
    r = (
        ctx.session.execute(
            text(
                "insert into tax_rates (country_code, label, rate_percent, source, created_by) "
                "values (:c, :l, :r, :s, :by) "
                "returning *"
            ),
            {"c": data.country_code, "l": data.label, "r": data.rate_percent, "s": data.source, "by": ctx.user.id},
        )
        .mappings()
        .one()
    )
    _log(ctx, "admin.tax_rate_added", "tax_rate", data.country_code, data.reason, rate=str(data.rate_percent))
    return TaxOut(**{k: r[k] for k in TaxOut.model_fields})


def fx(s: Any, base: str, quote: str) -> Decimal | None:
    if base == quote:
        return Decimal(1)
    r = s.scalar(
        text(
            "select rate from fx_rates where base = :b and quote = :q and effective_from <= now() "
            "order by effective_from desc limit 1"
        ),
        {"b": base, "q": quote},
    )
    if r is not None:
        return Decimal(r)
    inv = s.scalar(
        text(
            "select rate from fx_rates where base = :q and quote = :b and effective_from <= now() "
            "order by effective_from desc limit 1"
        ),
        {"b": base, "q": quote},
    )
    return (Decimal(1) / Decimal(inv)) if inv else None


# ------------------------------------------------------------------ organisations
class AdminSubOut(BaseModel):
    tenant_id: UUID
    tenant_name: str
    currency: str
    subscription_id: UUID | None
    plan: str | None
    pending_plan: str | None
    status: str | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    period_charges: Decimal
    open_invoices: int
    open_amount: Decimal


@router.get("/subscriptions", response_model=list[AdminSubOut])
def subscriptions(ctx: Ctx = Depends(platform_admin)) -> list[AdminSubOut]:
    rows = (
        ctx.session.execute(
            text(
                "select t.id as tenant_id, t.name as tenant_name, t.currency, s.id as subscription_id, p.name as plan, "
                "pp.name as pending_plan, s.status, s.current_period_end, coalesce(s.cancel_at_period_end, false) as "
                "cancel_at_period_end, coalesce((select sum(c.amount) from charge_ledger c "
                "where c.subscription_id = s.id "
                "and c.period_start = s.current_period_start), 0) as period_charges, "
                "(select count(*) from invoices i where i.tenant_id = t.id and i.status = 'open') as open_invoices, "
                "coalesce((select sum(i.total - i.amount_paid) from invoices i where i.tenant_id = t.id "
                "and i.status = 'open'), 0) as open_amount "
                "from tenants t left join subscriptions s on s.tenant_id = t.id and s.ended_at is null "
                "left join billing_plans p on p.id = s.plan_id left join billing_plans pp on pp.id = s.pending_plan_id "
                "order by t.name limit 500"
            )
        )
        .mappings()
        .all()
    )
    _log(ctx, "admin.subscriptions_listed", "subscription", None)
    return [AdminSubOut(**r) for r in rows]


class AssignIn(BaseModel):
    plan_id: UUID
    reason: str = Field(min_length=5, max_length=500)


@router.post("/tenants/{tenant_id}/subscription", response_model=AdminSubOut)
def assign_plan(tenant_id: UUID, data: AssignIn, ctx: Ctx = Depends(platform_admin)) -> AdminSubOut:
    t = _tenant(ctx, tenant_id)
    plan = _get_plan(ctx, data.plan_id)
    if plan["status"] != "active":
        raise conflict("plan_not_active", "Only an active plan can be assigned.")
    if plan["currency"] != t.currency:
        raise bad_request("currency_mismatch", f"This organisation is billed in {t.currency}.")
    with as_tenant(ctx, tenant_id):
        sub = billing.open_subscription(ctx.session)
        if sub is None:
            billing.subscribe(ctx.session, plan, source="platform_admin", membership_id=None)
        elif sub["plan_id"] != plan["id"]:
            ctx.session.execute(
                text(
                    "update subscriptions set pending_plan_id = :p, cancel_at_period_end = false, updated_at = now() "
                    "where id = :s"
                ),
                {"p": plan["id"], "s": sub["id"]},
            )
        else:
            raise conflict("same_plan", "The organisation is already on this plan.")
    _log(ctx, "admin.subscription_assigned", "tenant", str(tenant_id), data.reason, plan=plan["code"])
    return next(r for r in subscriptions(ctx) if r.tenant_id == tenant_id)


class CreditIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    reason: str = Field(min_length=5, max_length=500)


@router.post("/tenants/{tenant_id}/credits", response_model=AdminSubOut)
def credit(tenant_id: UUID, data: CreditIn, ctx: Ctx = Depends(platform_admin)) -> AdminSubOut:
    _tenant(ctx, tenant_id)
    with as_tenant(ctx, tenant_id):
        sub = billing.open_subscription(ctx.session)
        if sub is None:
            raise conflict("no_subscription", "The organisation has no subscription to credit.")
        billing._charge(
            ctx.session,
            sub,
            entry_type="credit",
            source_key=f"credit:{datetime.now(UTC).timestamp()}:{ctx.user.id}",
            amount=-data.amount,
            description="Credit",
            reason=data.reason,
            created_by=ctx.user.id,
        )
    _log(ctx, "admin.credit_issued", "tenant", str(tenant_id), data.reason, amount=str(data.amount))
    return next(r for r in subscriptions(ctx) if r.tenant_id == tenant_id)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


@router.post("/tenants/{tenant_id}/run")
def run_tenant(tenant_id: UUID, data: ReasonIn, ctx: Ctx = Depends(platform_admin)) -> dict:
    """Runs the billing job for one organisation now: closes any ended period and rates its usage."""
    _tenant(ctx, tenant_id)
    with as_tenant(ctx, tenant_id):
        issued = billing.close_due(ctx.session)
        rated = billing.rate(ctx.session)
    _log(ctx, "admin.billing_run", "tenant", str(tenant_id), data.reason, invoices=len(issued))
    return {"invoices_issued": [str(i) for i in issued], "charges_rated": rated}


@router.post("/tenants/{tenant_id}/close-period")
def close_period_now(tenant_id: UUID, data: ReasonIn, ctx: Ctx = Depends(platform_admin)) -> dict:
    """Ends the current period now and invoices it (for corrections and tests). The next period starts now."""
    _tenant(ctx, tenant_id)
    with as_tenant(ctx, tenant_id):
        sub = billing.open_subscription(ctx.session)
        if sub is None:
            raise conflict("no_subscription", "The organisation has no subscription.")
        now = datetime.now(UTC)
        ctx.session.execute(
            text("update subscriptions set current_period_end = :n, updated_at = now() where id = :s"),
            {"n": now, "s": sub["id"]},
        )
        issued = billing.close_due(ctx.session, now)
    _log(ctx, "admin.period_closed", "tenant", str(tenant_id), data.reason, invoices=len(issued))
    return {"invoices_issued": [str(i) for i in issued]}


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetail)
def get_invoice(invoice_id: UUID, ctx: Ctx = Depends(platform_admin)) -> InvoiceDetail:
    inv = ctx.session.execute(text("select * from invoices where id = :i"), {"i": invoice_id}).mappings().first()
    if inv is None:
        raise not_found("Invoice not found")
    _log(ctx, "admin.invoice_viewed", "invoice", str(invoice_id))
    return invoice_detail(ctx.session, inv)


@router.post("/invoices/{invoice_id}/void", response_model=InvoiceDetail)
def void_invoice(invoice_id: UUID, data: ReasonIn, ctx: Ctx = Depends(platform_admin)) -> InvoiceDetail:
    inv = ctx.session.execute(text("select * from invoices where id = :i"), {"i": invoice_id}).mappings().first()
    if inv is None:
        raise not_found("Invoice not found")
    if inv["status"] != "open" or inv["amount_paid"] > 0:
        raise conflict("not_voidable", "Only an open, unpaid invoice can be voided.")
    with as_tenant(ctx, inv["tenant_id"]):
        ctx.session.execute(
            text("update invoices set status = 'void', voided_at = now(), void_reason = :r where id = :i"),
            {"i": invoice_id, "r": data.reason},
        )
        billing.refresh_past_due(ctx.session)
    _log(ctx, "admin.invoice_voided", "invoice", str(invoice_id), data.reason, number=inv["number"])
    inv = ctx.session.execute(text("select * from invoices where id = :i"), {"i": invoice_id}).mappings().first()
    return invoice_detail(ctx.session, inv)


@router.post("/run")
def run_all(data: ReasonIn, ctx: Ctx = Depends(platform_admin)) -> dict:
    tenants = [
        r.tenant_id
        for r in ctx.session.execute(text("select tenant_id from subscriptions where ended_at is null")).all()
    ]
    issued = 0
    for t in tenants:
        with as_tenant(ctx, t):
            issued += len(billing.close_due(ctx.session))
            billing.rate(ctx.session)
    _log(ctx, "admin.billing_run", "platform", None, data.reason, organisations=len(tenants), invoices=issued)
    return {"organisations": len(tenants), "invoices_issued": issued}


# ------------------------------------------------------------------ overview
class CurrencyOverview(BaseModel):
    currency: str
    organisations: int
    active_subscriptions: int
    monthly_plan_fees: Decimal
    charges_this_month: Decimal
    provider_cost_this_month: Decimal | None
    provider_cost_unconverted: list[str]
    margin_this_month: Decimal | None
    open_invoice_amount: Decimal


@router.get("/overview", response_model=list[CurrencyOverview])
def overview(ctx: Ctx = Depends(platform_admin)) -> list[CurrencyOverview]:
    """Per billing currency. Provider cost is what XploVoice pays providers for organisations billed in that
    currency (usage on customers' own keys excluded), converted with the latest FX rate entered here."""
    s = ctx.session
    month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    out: list[CurrencyOverview] = []
    for cur in ("INR", "USD"):
        orgs = s.scalar(text("select count(*) from tenants where currency = :c"), {"c": cur}) or 0
        subs = s.execute(
            text(
                "select s.plan_id from subscriptions s join tenants t on t.id = s.tenant_id where t.currency = :c "
                "and s.ended_at is null and s.status in ('active', 'past_due')"
            ),
            {"c": cur},
        ).all()
        fees = Decimal(0)
        for r in subs:
            p = billing.prices(s, r.plan_id).get("base_fee")
            fees += p["unit_price"] if p else Decimal(0)
        charges = s.scalar(
            text("select coalesce(sum(amount), 0) from charge_ledger where currency = :c and occurred_at >= :m"),
            {"c": cur, "m": month},
        ) or Decimal(0)
        costs = s.execute(
            text(
                "select c.currency, sum(c.amount) as amt from provider_cost_ledger c "
                "join tenants t on t.id = c.tenant_id "
                "where t.currency = :c and c.priced and c.borne_by = 'platform' and c.created_at >= :m "
                "group by c.currency"
            ),
            {"c": cur, "m": month},
        ).all()
        cost = Decimal(0)
        missing: list[str] = []
        for r in costs:
            rate = fx(s, r.currency, cur)
            if rate is None:
                missing.append(r.currency)
            else:
                cost += Decimal(r.amt) * rate
        open_amt = s.scalar(
            text("select coalesce(sum(total - amount_paid), 0) from invoices where currency = :c and status = 'open'"),
            {"c": cur},
        ) or Decimal(0)
        out.append(
            CurrencyOverview(
                currency=cur,
                organisations=orgs,
                active_subscriptions=len(subs),
                monthly_plan_fees=fees,
                charges_this_month=Decimal(charges),
                provider_cost_this_month=None if missing else cost.quantize(Decimal("0.0001")),
                provider_cost_unconverted=missing,
                margin_this_month=None if missing else (Decimal(charges) - cost).quantize(Decimal("0.0001")),
                open_invoice_amount=Decimal(open_amt),
            )
        )
    _log(ctx, "admin.billing_overview", "platform", None)
    return out
