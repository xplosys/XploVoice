# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Tenant billing API (M15, Phase 7): plans, the subscription, spending limit and alerts, charges, invoices and
test payments. Reading needs billing:read (owner, admin); changing the plan, the limit or paying needs
billing:manage (owner)."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from ...core.context import Ctx, require
from ...core.errors import ApiError, bad_request, conflict, not_found, unauthorized
from ...core.permissions import Perm
from . import billing, payments

router = APIRouter(tags=["M15 billing"])
webhooks = APIRouter(prefix="/v1/webhooks", tags=["webhooks"], include_in_schema=False)


class PriceOut(BaseModel):
    meter: str
    label: str
    unit: str
    unit_price: Decimal
    included_quantity: Decimal
    monthly_cap: Decimal | None
    effective_from: datetime


class PlanOut(BaseModel):
    id: UUID
    code: str
    name: str
    description: str
    kind: str
    currency: str
    status: str
    is_default: bool
    trial_days: int
    limits: dict[str, int]
    prices: list[PriceOut]


class MeterUsage(BaseModel):
    meter: str
    label: str
    unit: str
    quantity: Decimal
    included_used: Decimal
    included_quantity: Decimal
    monthly_cap: Decimal | None
    unit_price: Decimal | None
    amount: Decimal


class SubscriptionOut(BaseModel):
    id: UUID
    status: str
    plan: PlanOut
    pending_plan: PlanOut | None
    started_at: datetime
    trial_ends_at: datetime | None
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    source: str


class SettingsOut(BaseModel):
    spend_limit: Decimal | None = None
    hard_limit: bool = False
    alert_percents: list[int] = [50, 80, 100]
    billing_email: str | None = None
    legal_name: str | None = None
    address: str | None = None
    tax_id: str | None = None


class AlertOut(BaseModel):
    kind: str
    threshold: int
    meter: str | None
    amount: Decimal | None
    created_at: datetime


class BillingOut(BaseModel):
    currency: str
    subscription: SubscriptionOut | None
    usage: list[MeterUsage]
    period_total: Decimal
    settings: SettingsOut
    alerts: list[AlertOut]
    blocked: dict[str, str] | None
    payment_providers: list[dict[str, str]]
    open_invoices: int


def price_out(p: Any) -> PriceOut:
    m = billing.METERS[p["meter"]]
    return PriceOut(
        meter=p["meter"],
        label=m.label,
        unit=m.unit,
        unit_price=p["unit_price"],
        included_quantity=p["included_quantity"],
        monthly_cap=p["monthly_cap"],
        effective_from=p["effective_from"],
    )


def plan_out(ctx_session: Any, plan: Any) -> PlanOut:
    current = billing.prices(ctx_session, plan["id"])
    order = list(billing.METERS)
    return PlanOut(
        id=plan["id"],
        code=plan["code"],
        name=plan["name"],
        description=plan["description"],
        kind=plan["kind"],
        currency=plan["currency"],
        status=plan["status"],
        is_default=plan["is_default"],
        trial_days=plan["trial_days"],
        limits=plan["limits"] or {},
        prices=[price_out(current[k]) for k in order if k in current],
    )


def _plan(s: Any, plan_id: UUID) -> Any | None:
    return s.execute(text("select * from billing_plans where id = :i"), {"i": plan_id}).mappings().first()


def _sub_out(s: Any, sub: Any) -> SubscriptionOut:
    plan = _plan(s, sub["plan_id"])
    pending = _plan(s, sub["pending_plan_id"]) if sub["pending_plan_id"] else None
    return SubscriptionOut(
        id=sub["id"],
        status=sub["status"],
        plan=plan_out(s, plan),
        pending_plan=plan_out(s, pending) if pending else None,
        started_at=sub["started_at"],
        trial_ends_at=sub["trial_ends_at"],
        current_period_start=sub["current_period_start"],
        current_period_end=sub["current_period_end"],
        cancel_at_period_end=sub["cancel_at_period_end"],
        source=sub["source"],
    )


def _settings(s: Any) -> SettingsOut:
    r = billing.settings_row(s)
    if r is None:
        return SettingsOut()
    return SettingsOut(**{k: r[k] for k in SettingsOut.model_fields})


@router.get("/v1/billing/plans", response_model=list[PlanOut])
def list_plans(ctx: Ctx = Depends(require(Perm.BILLING_READ))) -> list[PlanOut]:
    rows = (
        ctx.session.execute(
            text("select * from billing_plans where status = 'active' and currency = :c order by name"),
            {"c": ctx.tenant.currency},
        )
        .mappings()
        .all()
    )
    return [plan_out(ctx.session, r) for r in rows]


@router.get("/v1/billing", response_model=BillingOut)
def overview(ctx: Ctx = Depends(require(Perm.BILLING_READ))) -> BillingOut:
    s = ctx.session
    sub = billing.open_subscription(s)
    usage: list[MeterUsage] = []
    total = Decimal(0)
    alerts: list[AlertOut] = []
    if sub:
        billing.rate(s, sub)
        current = billing.prices(s, sub["plan_id"])
        used = billing.period_usage(s, sub)
        for key, m in billing.METERS.items():
            p, u = current.get(key), used.get(key)
            if p is None and u is None:
                continue
            usage.append(
                MeterUsage(
                    meter=key,
                    label=m.label,
                    unit=m.unit,
                    quantity=u["quantity"] if u else Decimal(0),
                    included_used=u["included"] if u else Decimal(0),
                    included_quantity=p["included_quantity"] if p else Decimal(0),
                    monthly_cap=p["monthly_cap"] if p else None,
                    unit_price=p["unit_price"] if p else None,
                    amount=u["amount"] if u else Decimal(0),
                )
            )
        total = billing.period_total(s, sub)
        alerts = [
            AlertOut(
                kind=a.kind, threshold=a.threshold, meter=a.meter or None, amount=a.amount, created_at=a.created_at
            )
            for a in s.execute(
                text("select * from billing_alerts where subscription_id = :s and period_start = :ps order by id"),
                {"s": sub["id"], "ps": sub["current_period_start"]},
            ).all()
        ]
    block = billing.admission(s, "call")
    providers = [
        dict(r._mapping)
        for r in s.execute(text("select key, name, status, description from payment_providers order by key")).all()
    ]
    open_invoices = (
        s.scalar(text("select count(*) from invoices where tenant_id = app_tenant_id() and status = 'open'")) or 0
    )
    return BillingOut(
        currency=sub["currency"] if sub else ctx.tenant.currency,
        subscription=_sub_out(s, billing.open_subscription(s)) if sub else None,
        usage=usage,
        period_total=total,
        settings=_settings(s),
        alerts=alerts,
        blocked={"code": block.code, "message": block.message} if block else None,
        payment_providers=providers,
        open_invoices=open_invoices,
    )


class ChoosePlanIn(BaseModel):
    plan_id: UUID


@router.post("/v1/billing/subscription", response_model=SubscriptionOut)
def choose_plan(data: ChoosePlanIn, ctx: Ctx = Depends(require(Perm.BILLING_MANAGE))) -> SubscriptionOut:
    s = ctx.session
    plan = _plan(s, data.plan_id)
    if plan is None or plan["status"] != "active":
        raise not_found("Plan not found")
    if plan["currency"] != ctx.tenant.currency:
        raise bad_request(
            "currency_mismatch",
            f"This plan is billed in {plan['currency']}; your organisation uses {ctx.tenant.currency}.",
        )
    sub = billing.open_subscription(s)
    if sub is None:
        billing.subscribe(s, plan, source="self_service", membership_id=ctx.membership.id)
        ctx.audit("subscription.started", resource_type="plan", resource_id=str(plan["id"]), plan=plan["code"])
    else:
        if sub["plan_id"] == plan["id"]:
            if sub["pending_plan_id"] or sub["cancel_at_period_end"]:
                s.execute(
                    text(
                        "update subscriptions set pending_plan_id = null, cancel_at_period_end = false, "
                        "updated_at = now() where id = :s"
                    ),
                    {"s": sub["id"]},
                )
                ctx.audit("subscription.change_cancelled", resource_type="subscription", resource_id=str(sub["id"]))
            else:
                raise conflict("same_plan", "You are already on this plan.")
        elif sub["pending_plan_id"] == plan["id"]:
            raise conflict("already_scheduled", "This plan already starts when the current period ends.")
        else:
            # Changes apply when the current period ends, so the period is billed on one plan.
            s.execute(
                text(
                    "update subscriptions set pending_plan_id = :p, cancel_at_period_end = false, updated_at = now() "
                    "where id = :s"
                ),
                {"s": sub["id"], "p": plan["id"]},
            )
            ctx.audit(
                "subscription.change_scheduled",
                resource_type="subscription",
                resource_id=str(sub["id"]),
                plan=plan["code"],
            )
    out = billing.open_subscription(s)
    assert out is not None
    return _sub_out(s, out)


@router.post("/v1/billing/subscription/cancel", response_model=SubscriptionOut)
def cancel(ctx: Ctx = Depends(require(Perm.BILLING_MANAGE))) -> SubscriptionOut:
    s = ctx.session
    sub = billing.open_subscription(s)
    if sub is None:
        raise not_found("No subscription")
    s.execute(
        text(
            "update subscriptions set cancel_at_period_end = true, pending_plan_id = null, cancelled_at = now(), "
            "updated_at = now() where id = :s"
        ),
        {"s": sub["id"]},
    )
    ctx.audit("subscription.cancel_scheduled", resource_type="subscription", resource_id=str(sub["id"]))
    out = billing.open_subscription(s)
    assert out is not None
    return _sub_out(s, out)


@router.post("/v1/billing/subscription/resume", response_model=SubscriptionOut)
def resume(ctx: Ctx = Depends(require(Perm.BILLING_MANAGE))) -> SubscriptionOut:
    s = ctx.session
    sub = billing.open_subscription(s)
    if sub is None:
        raise not_found("No subscription")
    if not sub["cancel_at_period_end"]:
        raise conflict("not_cancelling", "The subscription is not set to end.")
    s.execute(
        text(
            "update subscriptions set cancel_at_period_end = false, cancelled_at = null, updated_at = now() "
            "where id = :s"
        ),
        {"s": sub["id"]},
    )
    ctx.audit("subscription.resumed", resource_type="subscription", resource_id=str(sub["id"]))
    out = billing.open_subscription(s)
    assert out is not None
    return _sub_out(s, out)


class SettingsIn(BaseModel):
    spend_limit: Decimal | None = Field(default=None, gt=0, max_digits=16, decimal_places=2)
    hard_limit: bool = False
    alert_percents: list[int] = Field(default=[50, 80, 100], max_length=6)
    billing_email: EmailStr | None = None
    legal_name: str | None = Field(default=None, max_length=160)
    address: str | None = Field(default=None, max_length=500)
    tax_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{5,20}$")

    @field_validator("alert_percents")
    @classmethod
    def _pcts(cls, v: list[int]) -> list[int]:
        allowed = {25, 50, 75, 80, 90, 100}
        if any(p not in allowed for p in v):
            raise ValueError("Alert levels must be 25, 50, 75, 80, 90 or 100 percent")
        return sorted(set(v))


@router.get("/v1/billing/settings", response_model=SettingsOut)
def get_settings_(ctx: Ctx = Depends(require(Perm.BILLING_READ))) -> SettingsOut:
    return _settings(ctx.session)


@router.put("/v1/billing/settings", response_model=SettingsOut)
def put_settings(data: SettingsIn, ctx: Ctx = Depends(require(Perm.BILLING_MANAGE))) -> SettingsOut:
    v = data.model_dump()
    v["billing_email"] = str(v["billing_email"]) if v["billing_email"] else None
    ctx.session.execute(
        text(
            "insert into billing_settings (tenant_id, spend_limit, hard_limit, alert_percents, billing_email, "
            "legal_name, address, tax_id, updated_by_membership_id, updated_at) values (app_tenant_id(), :spend_limit, "
            ":hard_limit, :alert_percents, :billing_email, :legal_name, :address, :tax_id, :m, now()) "
            "on conflict (tenant_id) do update set spend_limit = excluded.spend_limit, "
            "hard_limit = excluded.hard_limit, "
            "alert_percents = excluded.alert_percents, billing_email = excluded.billing_email, "
            "legal_name = excluded.legal_name, address = excluded.address, tax_id = excluded.tax_id, "
            "updated_by_membership_id = excluded.updated_by_membership_id, updated_at = now()"
        ),
        {**v, "m": ctx.membership.id},
    )
    ctx.audit(
        "billing.settings_updated",
        resource_type="billing_settings",
        spend_limit=str(data.spend_limit) if data.spend_limit else None,
        hard_limit=data.hard_limit,
    )
    return _settings(ctx.session)


class LedgerOut(BaseModel):
    id: int
    entry_type: str
    meter: str | None
    description: str
    quantity: Decimal
    included_applied: Decimal
    unit_price: Decimal | None
    amount: Decimal
    currency: str
    occurred_at: datetime
    period_start: datetime
    reason: str | None


@router.get("/v1/billing/ledger", response_model=list[LedgerOut])
def ledger(
    ctx: Ctx = Depends(require(Perm.BILLING_READ)), limit: int = Query(50, ge=1, le=500), before_id: int | None = None
) -> list[LedgerOut]:
    rows = (
        ctx.session.execute(
            text(
                "select * from charge_ledger where tenant_id = app_tenant_id() "
                "and (cast(:b as bigint) is null or id < :b) "
                "order by id desc limit :l"
            ),
            {"b": before_id, "l": limit},
        )
        .mappings()
        .all()
    )
    return [LedgerOut(**{k: r[k] for k in LedgerOut.model_fields}) for r in rows]


class InvoiceLineOut(BaseModel):
    position: int
    entry_type: str
    meter: str | None
    description: str
    quantity: Decimal
    included_quantity: Decimal
    unit_price: Decimal | None
    amount: Decimal


class PaymentOut(BaseModel):
    id: UUID
    provider_key: str
    amount: Decimal
    currency: str
    status: str
    failure_reason: str | None
    created_at: datetime
    completed_at: datetime | None


class InvoiceOut(BaseModel):
    id: UUID
    number: str
    plan_name: str
    period_start: datetime
    period_end: datetime
    currency: str
    subtotal: Decimal
    tax_label: str | None
    tax_percent: Decimal | None
    tax_amount: Decimal
    total: Decimal
    amount_paid: Decimal
    status: str
    issued_at: datetime
    due_at: datetime
    paid_at: datetime | None
    voided_at: datetime | None
    void_reason: str | None


class InvoiceDetail(InvoiceOut):
    bill_to: dict[str, Any]
    seller: dict[str, str]
    lines: list[InvoiceLineOut]
    payments: list[PaymentOut]


SELLER = {"name": "Xplosys", "product": "XploVoice"}


def invoice_detail(s: Any, inv: Any) -> InvoiceDetail:
    lines = (
        s.execute(text("select * from invoice_lines where invoice_id = :i order by position"), {"i": inv["id"]})
        .mappings()
        .all()
    )
    pays = (
        s.execute(text("select * from payments where invoice_id = :i order by created_at"), {"i": inv["id"]})
        .mappings()
        .all()
    )
    return InvoiceDetail(
        **{k: inv[k] for k in InvoiceOut.model_fields},
        bill_to=inv["bill_to"] or {},
        seller=SELLER,
        lines=[InvoiceLineOut(**{k: r[k] for k in InvoiceLineOut.model_fields}) for r in lines],
        payments=[PaymentOut(**{k: r[k] for k in PaymentOut.model_fields}) for r in pays],
    )


@router.get("/v1/billing/invoices", response_model=list[InvoiceOut])
def list_invoices(ctx: Ctx = Depends(require(Perm.BILLING_READ))) -> list[InvoiceOut]:
    rows = (
        ctx.session.execute(
            text("select * from invoices where tenant_id = app_tenant_id() order by issued_at desc limit 200")
        )
        .mappings()
        .all()
    )
    return [InvoiceOut(**{k: r[k] for k in InvoiceOut.model_fields}) for r in rows]


def _invoice(ctx: Ctx, invoice_id: UUID) -> Any:
    inv = (
        ctx.session.execute(
            text("select * from invoices where id = :i and tenant_id = app_tenant_id()"), {"i": invoice_id}
        )
        .mappings()
        .first()
    )
    if inv is None:
        raise not_found("Invoice not found")
    return inv


@router.get("/v1/billing/invoices/{invoice_id}", response_model=InvoiceDetail)
def get_invoice(invoice_id: UUID, ctx: Ctx = Depends(require(Perm.BILLING_READ))) -> InvoiceDetail:
    return invoice_detail(ctx.session, _invoice(ctx, invoice_id))


class PayIn(BaseModel):
    provider: Literal["test", "gateway"] = "test"
    outcome: Literal["succeed", "decline"] = "succeed"


@router.post("/v1/billing/invoices/{invoice_id}/pay", response_model=PaymentOut)
async def pay_invoice(invoice_id: UUID, data: PayIn, ctx: Ctx = Depends(require(Perm.BILLING_MANAGE))) -> PaymentOut:
    if data.provider == "gateway":
        raise ApiError(503, "awaiting_configuration", "Online payments are awaiting a payment gateway contract.")
    try:
        payments.test_allowed()
    except payments.PaymentError as e:
        raise bad_request("provider_unavailable", str(e)) from None
    inv = _invoice(ctx, invoice_id)
    if inv["status"] != "open":
        raise conflict("not_open", "Only an open invoice can be paid.")
    due = inv["total"] - inv["amount_paid"]
    ref = payments.new_ref()
    pending = ctx.session.scalar(
        text("select id from payments where invoice_id = :i and status = 'pending'"), {"i": invoice_id}
    )
    if pending:
        raise conflict("payment_pending", "A payment for this invoice is already in progress.")
    pid = ctx.session.scalar(
        text(
            "insert into payments (tenant_id, invoice_id, provider_key, provider_ref, amount, currency, "
            "created_by_membership_id) values (app_tenant_id(), :i, 'test', :r, :a, :c, :m) returning id"
        ),
        {"i": invoice_id, "r": ref, "a": due, "c": inv["currency"], "m": ctx.membership.id},
    )
    ctx.audit("payment.started", resource_type="invoice", resource_id=str(invoice_id), provider="test", amount=str(due))
    ctx.commit()  # the provider's webhook is handled in its own transaction
    body, sig = payments.test_settlement(ref, due, inv["currency"], data.outcome)
    await _receive("test", body, sig)
    pay = payments.payment_for(ctx.session, pid)
    return PaymentOut(**{k: pay[k] for k in PaymentOut.model_fields})


async def _receive(provider: str, body: bytes, signature: str | None) -> str:
    import json

    if not payments.verify(body, signature):
        raise unauthorized("bad_signature", "Invalid webhook signature")
    try:
        event = json.loads(body)
    except ValueError:
        raise bad_request("bad_body", "Webhook body is not JSON") from None
    return await run_in_threadpool(payments.handle_event, provider, event)


@webhooks.post("/payments/test")
async def test_payment_webhook(request: Request, x_test_signature: str | None = Header(default=None)) -> dict:
    try:
        payments.test_allowed()
    except payments.PaymentError:
        raise not_found() from None
    body = await request.body()
    if len(body) > 16 * 1024:
        raise bad_request("too_large", "Webhook body is too large")
    return {"result": await _receive("test", body, x_test_signature)}
