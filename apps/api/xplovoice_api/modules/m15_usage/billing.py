# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Tenant charging (M15, Phase 7): rating, subscription periods, spending limits, quotas, cost alerts and invoices.

- Rating turns measured usage (AI usage events in provider units, telephony billed seconds) into charges at the
  plan price in force when the usage happened. Only XploVoice-managed AI usage is charged; usage on a customer's
  own provider key is the customer's cost (CR-018). Each charge has a unique source key, so rating twice is a
  no-op. Provider cost stays in its own ledger and is never used as the tenant price.
- A subscription runs in monthly periods. The base fee is charged at the start of each period (waived during a
  trial). When a period ends, it is rated to its end and invoiced; a pending plan change or cancellation applies
  then.
- Admission: new calls, chats and AI requests are refused when the organisation is over its hard spending limit,
  has used up a plan quota, or has an overdue invoice. A call already in progress is never cut off.

Every function expects a session whose RLS context is the tenant's.
"""

import calendar
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...core import audit
from ...core.config import get_settings
from ..m13_integrations.events import emit

log = logging.getLogger(__name__)

CENT = Decimal("0.01")
FINE = Decimal("0.000000000001")


@dataclass(frozen=True)
class Meter:
    key: str
    label: str
    unit: str  # what one unit of unit_price buys
    purpose: str  # which admissions a quota on this meter blocks: "call" or "ai"


METERS: dict[str, Meter] = {
    m.key: m
    for m in (
        Meter("base_fee", "Plan fee", "month", ""),
        Meter("phone_inbound_minute", "Inbound phone minutes", "minute", "call"),
        Meter("phone_outbound_minute", "Outbound phone minutes", "minute", "call"),
        Meter("llm_input_1k_tokens", "AI input tokens", "1,000 tokens", "ai"),
        Meter("llm_output_1k_tokens", "AI output tokens", "1,000 tokens", "ai"),
        Meter("stt_minute", "Speech-to-text", "minute", "ai"),
        Meter("tts_1k_characters", "Text-to-speech", "1,000 characters", "ai"),
    )
}
USAGE_METERS = tuple(k for k in METERS if k != "base_fee")

# (usage_events.kind, usage_events.unit) -> (meter, divisor into the meter's unit)
AI_METERS: dict[tuple[str, str], tuple[str, Decimal]] = {
    ("llm", "input_token"): ("llm_input_1k_tokens", Decimal(1000)),
    ("llm", "output_token"): ("llm_output_1k_tokens", Decimal(1000)),
    ("stt", "audio_second"): ("stt_minute", Decimal(60)),
    ("tts", "character"): ("tts_1k_characters", Decimal(1000)),
}


@dataclass
class Block:
    code: str
    message: str


# ------------------------------------------------------------------ periods
def add_month(dt: datetime, anchor_day: int) -> datetime:
    """The same day next month, clamped to the month's last day (31 Jan -> 28/29 Feb -> 31 Mar)."""
    y, m = (dt.year + 1, 1) if dt.month == 12 else (dt.year, dt.month + 1)
    day = min(anchor_day, calendar.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=day)


def first_period(start: datetime, trial_days: int) -> tuple[datetime, datetime, datetime | None]:
    if trial_days > 0:
        end = start + timedelta(days=trial_days)
        return start, end, end
    return start, add_month(start, start.day), None


# ------------------------------------------------------------------ reads
def open_subscription(s: Session) -> Any | None:
    return (
        s.execute(
            text(
                "select s.*, p.name as plan_name, p.code as plan_code, p.kind as plan_kind, p.currency, p.limits "
                "from subscriptions s join billing_plans p on p.id = s.plan_id "
                "where s.tenant_id = app_tenant_id() and s.ended_at is null"
            )
        )
        .mappings()
        .first()
    )


def settings_row(s: Session) -> Any | None:
    return s.execute(text("select * from billing_settings where tenant_id = app_tenant_id()")).mappings().first()


def prices(s: Session, plan_id: UUID, at: datetime | None = None) -> dict[str, Any]:
    """The price in force for each meter at `at` (default now)."""
    rows = (
        s.execute(
            text(
                "select distinct on (meter) * from plan_prices where plan_id = :p and effective_from <= :at "
                "order by meter, effective_from desc"
            ),
            {"p": plan_id, "at": at or datetime.now(UTC)},
        )
        .mappings()
        .all()
    )
    return {r["meter"]: r for r in rows}


def _price_history(s: Session, plan_id: UUID) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for r in (
        s.execute(text("select * from plan_prices where plan_id = :p order by effective_from desc"), {"p": plan_id})
        .mappings()
        .all()
    ):
        out.setdefault(r["meter"], []).append(r)
    return out


def _price_at(history: dict[str, list[Any]], meter: str, at: datetime) -> Any | None:
    for r in history.get(meter, []):
        if r["effective_from"] <= at:
            return r
    return None


def period_usage(s: Session, sub: Any) -> dict[str, dict[str, Decimal]]:
    rows = s.execute(
        text(
            "select meter, sum(quantity) as q, sum(included_applied) as inc, sum(amount) as amt from charge_ledger "
            "where subscription_id = :s and period_start = :ps and meter is not null group by meter"
        ),
        {"s": sub["id"], "ps": sub["current_period_start"]},
    ).all()
    return {r.meter: {"quantity": r.q, "included": r.inc, "amount": r.amt} for r in rows}


def period_total(s: Session, sub: Any) -> Decimal:
    return s.scalar(
        text("select coalesce(sum(amount), 0) from charge_ledger where subscription_id = :s and period_start = :ps"),
        {"s": sub["id"], "ps": sub["current_period_start"]},
    ) or Decimal(0)


def plan_limit(s: Session, key: str) -> int | None:
    sub = open_subscription(s)
    if sub is None:
        return None
    v = (sub["limits"] or {}).get(key)
    return int(v) if v is not None else None


def max_concurrent_calls(s: Session) -> int:
    """The platform ceiling, lowered by the plan's limit when it has one."""
    ceiling = get_settings().max_concurrent_calls_per_tenant
    limit = plan_limit(s, "max_concurrent_calls")
    return min(ceiling, limit) if limit is not None else ceiling


# ------------------------------------------------------------------ rating
def _lock(s: Session, tenant_id: UUID) -> None:
    s.execute(text("select pg_advisory_xact_lock(hashtext(:k))"), {"k": f"billing:{tenant_id}"})


def _charge(s: Session, sub: Any, **v: Any) -> bool:
    row = s.execute(
        text(
            "insert into charge_ledger (tenant_id, subscription_id, period_start, entry_type, meter, source_key, "
            "quantity, included_applied, unit_price, plan_price_id, amount, currency, usage_event_id, "
            "telephony_usage_id, occurred_at, description, reason, created_by) values (app_tenant_id(), :sub, :ps, "
            ":type, :meter, :key, :q, :inc, :up, :pp, :amt, :cur, :ue, :tu, coalesce(:at, now()), :desc, :reason, "
            ":by) on conflict (tenant_id, source_key) do nothing returning id"
        ),
        {
            "sub": sub["id"],
            "ps": v.get("period_start", sub["current_period_start"]),
            "type": v["entry_type"],
            "meter": v.get("meter"),
            "key": v["source_key"],
            "q": v.get("quantity", Decimal(0)),
            "inc": v.get("included", Decimal(0)),
            "up": v.get("unit_price"),
            "pp": v.get("plan_price_id"),
            "amt": v["amount"],
            "cur": sub["currency"],
            "ue": v.get("usage_event_id"),
            "tu": v.get("telephony_usage_id"),
            "at": v.get("occurred_at"),
            "desc": v.get("description", ""),
            "reason": v.get("reason"),
            "by": v.get("created_by"),
        },
    ).first()
    return row is not None


def _charge_fee(s: Session, sub: Any) -> None:
    start = sub["current_period_start"]
    if sub["status"] == "trialing":
        return  # base fee waived during the trial
    price = prices(s, sub["plan_id"], start).get("base_fee")
    if price is None or price["unit_price"] <= 0:
        return
    if s.scalar(
        text("select 1 from charge_ledger where subscription_id = :s and period_start = :ps and entry_type = 'fee'"),
        {"s": sub["id"], "ps": start},
    ):
        return  # one fee per period (callers hold the billing lock)
    _charge(
        s,
        sub,
        entry_type="fee",
        meter="base_fee",
        source_key=f"fee:{sub['id']}:{start.isoformat()}",
        quantity=Decimal(1),
        unit_price=price["unit_price"],
        plan_price_id=price["id"],
        amount=price["unit_price"],
        occurred_at=start,
        description=f"{sub['plan_name']} plan fee",
    )


def rate(s: Session, sub: Any | None = None, *, until: datetime | None = None) -> int:
    """Charges every unrated usage record of the open subscription up to `until` (default now) into its current
    period. Returns how many charges were written."""
    sub = sub or open_subscription(s)
    if sub is None:
        return 0
    _lock(s, sub["tenant_id"])
    _charge_fee(s, sub)
    until = until or datetime.now(UTC)
    history = _price_history(s, sub["plan_id"])
    used = {m: v["included"] for m, v in period_usage(s, sub).items()}
    written = 0

    def one(meter: str, qty: Decimal, at: datetime, key: str, **refs: Any) -> None:
        nonlocal written
        price = _price_at(history, meter, at)
        included = price["included_quantity"] if price else Decimal(0)
        left = max(Decimal(0), included - used.get(meter, Decimal(0)))
        applied = min(qty, left)
        unit_price = price["unit_price"] if price else Decimal(0)
        amount = ((qty - applied) * unit_price).quantize(FINE)
        if _charge(
            s,
            sub,
            entry_type="usage",
            meter=meter,
            source_key=key,
            quantity=qty,
            included=applied,
            unit_price=unit_price if price else None,
            plan_price_id=price["id"] if price else None,
            amount=amount,
            occurred_at=at,
            description=METERS[meter].label if price else f"{METERS[meter].label} (not charged on this plan)",
            **refs,
        ):
            used[meter] = used.get(meter, Decimal(0)) + applied
            written += 1

    ai = s.execute(
        text(
            "select u.id, u.kind, u.unit, u.quantity, u.occurred_at from usage_events u "
            "where u.tenant_id = app_tenant_id() and u.account = 'managed' "
            "and (u.kind, u.unit) in (('llm', 'input_token'), ('llm', 'output_token'), ('stt', 'audio_second'), "
            "('tts', 'character')) and u.occurred_at >= :since and u.occurred_at < :until "
            "and not exists (select 1 from charge_ledger c where c.usage_event_id = u.id) order by u.id limit 5000"
        ),
        {"since": sub["started_at"], "until": until},
    ).all()
    for r in ai:
        meter, div = AI_METERS[(r.kind, r.unit)]
        one(
            meter,
            (Decimal(r.quantity) / div).quantize(Decimal("0.000001")),
            r.occurred_at,
            f"ai:{r.id}",
            usage_event_id=r.id,
        )
    phone = s.execute(
        text(
            "select t.id, t.direction, t.billed_seconds, t.created_at from telephony_usage t "
            "where t.tenant_id = app_tenant_id() and t.created_at >= :since and t.created_at < :until "
            "and not exists (select 1 from charge_ledger c where c.telephony_usage_id = t.id) order by t.id limit 5000"
        ),
        {"since": sub["started_at"], "until": until},
    ).all()
    for r in phone:
        meter = f"phone_{r.direction}_minute"
        one(
            meter,
            (Decimal(r.billed_seconds) / 60).quantize(Decimal("0.000001")),
            r.created_at,
            f"tel:{r.id}",
            telephony_usage_id=r.id,
        )
    _alerts(s, sub, history)
    return written


def _alerts(s: Session, sub: Any, history: dict[str, list[Any]]) -> None:
    """Records each cost alert once per period: spend thresholds of the spending limit, and used-up quotas."""
    cfg = settings_row(s)
    now = datetime.now(UTC)
    fired: list[dict[str, Any]] = []
    if cfg and cfg["spend_limit"]:
        total = period_total(s, sub)
        for pct in sorted(cfg["alert_percents"] or []):
            if total >= cfg["spend_limit"] * Decimal(pct) / 100:
                fired.append({"kind": "spend_threshold", "threshold": pct, "meter": "", "amount": total})
    usage = period_usage(s, sub)
    for meter, v in usage.items():
        price = _price_at(history, meter, now)
        if price is not None and price["monthly_cap"] is not None and v["quantity"] >= price["monthly_cap"]:
            fired.append({"kind": "quota_reached", "threshold": 100, "meter": meter, "amount": v["quantity"]})
    for a in fired:
        row = s.execute(
            text(
                "insert into billing_alerts (tenant_id, subscription_id, period_start, kind, threshold, meter, "
                "amount, currency) values (app_tenant_id(), :s, :ps, :k, :th, :m, :amt, :cur) "
                "on conflict do nothing returning id"
            ),
            {
                "s": sub["id"],
                "ps": sub["current_period_start"],
                "k": a["kind"],
                "th": a["threshold"],
                "m": a["meter"],
                "amt": a["amount"],
                "cur": sub["currency"],
            },
        ).first()
        if row is None:
            continue
        audit.record(
            s,
            action="billing.alert",
            result="success",
            tenant_id=sub["tenant_id"],
            actor_kind="service",
            resource_type="subscription",
            resource_id=str(sub["id"]),
            metadata={"kind": a["kind"], "threshold": a["threshold"], "meter": a["meter"]},
        )
        emit(
            s,
            sub["tenant_id"],
            "billing.alert",
            {
                "kind": a["kind"],
                "threshold": a["threshold"],
                "meter": a["meter"] or None,
                "amount": str(a["amount"]),
                "currency": sub["currency"],
            },
        )


# ------------------------------------------------------------------ admission
def admission(s: Session, purpose: str) -> Block | None:
    """Whether the organisation may start something new that costs money: purpose "call" (browser, phone and
    campaign calls, text chats) or "ai" (playground requests)."""
    settings = get_settings()
    sub = open_subscription(s)
    if sub is None:
        if settings.billing_require_plan:
            return Block("no_plan", "Choose a plan on the Billing page first.")
        return None
    if sub["status"] == "past_due" and settings.billing_block_past_due:
        return Block("invoice_overdue", "An invoice is overdue. Pay it on the Billing page to continue.")
    rate(s, sub)
    cfg = settings_row(s)
    if cfg and cfg["spend_limit"] and cfg["hard_limit"] and period_total(s, sub) >= cfg["spend_limit"]:
        return Block(
            "spend_limit_reached",
            "This month's spending limit is reached. Raise it on the Billing page to continue.",
        )
    current = prices(s, sub["plan_id"])
    for meter, v in period_usage(s, sub).items():
        p = current.get(meter)
        relevant = METERS[meter].purpose == purpose or purpose == "call"
        if relevant and p is not None and p["monthly_cap"] is not None and v["quantity"] >= p["monthly_cap"]:
            return Block("quota_reached", f"This month's {METERS[meter].label.lower()} quota on your plan is used up.")
    return None


def enforce(s: Session, purpose: str) -> None:
    """Raises 402 with the reason when billing refuses something new."""
    from ...core.errors import ApiError

    block = admission(s, purpose)
    if block is not None:
        raise ApiError(402, block.code, block.message)


# ------------------------------------------------------------------ subscribe, change, cancel
def subscribe(s: Session, plan: Any, *, source: str, membership_id: UUID | None) -> UUID:
    now = datetime.now(UTC)
    start, end, trial_end = first_period(now, plan["trial_days"])
    sid = s.scalar(
        text(
            "insert into subscriptions (tenant_id, plan_id, status, started_at, trial_ends_at, current_period_start, "
            "current_period_end, source, created_by_membership_id) values (app_tenant_id(), :p, :st, :now, :te, "
            ":ps, :pe, :src, :m) returning id"
        ),
        {
            "p": plan["id"],
            "st": "trialing" if trial_end else "active",
            "now": now,
            "te": trial_end,
            "ps": start,
            "pe": end,
            "src": source,
            "m": membership_id,
        },
    )
    sub = open_subscription(s)
    assert sub is not None
    _lock(s, sub["tenant_id"])
    _charge_fee(s, sub)
    return sid


def default_plan_for(s: Session, currency: str) -> Any | None:
    return (
        s.execute(
            text("select * from billing_plans where currency = :c and is_default and status = 'active'"),
            {"c": currency},
        )
        .mappings()
        .first()
    )


# ------------------------------------------------------------------ period close and invoices
def _money(v: Decimal) -> Decimal:
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


def _tax_for(s: Session, country: str, at: datetime) -> Any | None:
    return (
        s.execute(
            text(
                "select * from tax_rates where country_code = :c and effective_from <= :at "
                "order by effective_from desc limit 1"
            ),
            {"c": country, "at": at},
        )
        .mappings()
        .first()
    )


ORDER = {"fee": 0, "usage": 1, "adjustment": 2, "credit": 3}


def issue_invoice(s: Session, sub: Any) -> UUID | None:
    existing = s.scalar(
        text("select id from invoices where subscription_id = :s and period_start = :ps"),
        {"s": sub["id"], "ps": sub["current_period_start"]},
    )
    if existing:
        return existing
    groups = s.execute(
        text(
            "select entry_type, meter, unit_price, min(description) as description, min(reason) as reason, "
            "sum(quantity) as q, sum(included_applied) as inc, sum(amount) as amt from charge_ledger "
            "where subscription_id = :s and period_start = :ps "
            "and not (entry_type = 'usage' and plan_price_id is null) "  # use the plan doesn't charge for stays off
            "group by entry_type, meter, unit_price, case when entry_type in ('credit', 'adjustment') then id end"
        ),
        {"s": sub["id"], "ps": sub["current_period_start"]},
    ).all()
    lines = sorted(groups, key=lambda g: (ORDER[g.entry_type], g.meter or "", g.unit_price or 0))
    subtotal = sum((_money(g.amt) for g in lines), Decimal(0))
    tenant = s.execute(text("select name, country_code from tenants where id = app_tenant_id()")).first()
    assert tenant is not None
    end = sub["current_period_end"]
    tax = _tax_for(s, tenant.country_code, datetime.now(UTC))  # the rate in force when the invoice is issued
    tax_amount = _money(subtotal * tax["rate_percent"] / 100) if tax and subtotal > 0 else Decimal(0)
    total = subtotal + tax_amount
    cfg = settings_row(s)
    bill_to = {
        "name": (cfg and cfg["legal_name"]) or tenant.name,
        "address": cfg and cfg["address"],
        "tax_id": cfg and cfg["tax_id"],
        "email": cfg and cfg["billing_email"],
    }
    seq = s.scalar(text("select nextval('invoice_number_seq')"))
    number = f"XV-{end.year}-{seq:06d}"
    now = datetime.now(UTC)
    inv_id = s.scalar(
        text(
            "insert into invoices (tenant_id, number, subscription_id, plan_name, period_start, period_end, currency, "
            "subtotal, tax_label, tax_percent, tax_amount, total, status, bill_to, issued_at, due_at, paid_at) values "
            "(app_tenant_id(), :n, :s, :plan, :ps, :pe, :cur, :sub, :tl, :tp, :ta, :tot, :st, cast(:bt as jsonb), "
            ":now, :due, :paid) returning id"
        ),
        {
            "n": number,
            "s": sub["id"],
            "plan": sub["plan_name"],
            "ps": sub["current_period_start"],
            "pe": end,
            "cur": sub["currency"],
            "sub": subtotal,
            "tl": tax["label"] if tax else None,
            "tp": tax["rate_percent"] if tax else None,
            "ta": tax_amount,
            "tot": total,
            "st": "paid" if total <= 0 else "open",
            "bt": json.dumps(bill_to),
            "now": now,
            "due": now + timedelta(days=get_settings().billing_invoice_due_days),
            "paid": now if total <= 0 else None,
        },
    )
    for i, g in enumerate(lines, start=1):
        desc = g.description
        if g.entry_type in ("credit", "adjustment") and g.reason:
            desc = f"{desc}: {g.reason}" if desc else g.reason
        s.execute(
            text(
                "insert into invoice_lines (tenant_id, invoice_id, position, entry_type, meter, description, quantity, "
                "included_quantity, unit_price, amount) values (app_tenant_id(), :i, :pos, :t, :m, :d, :q, :inc, :up, "
                ":amt)"
            ),
            {
                "i": inv_id,
                "pos": i,
                "t": g.entry_type,
                "m": g.meter,
                "d": desc or g.entry_type,
                "q": g.q,
                "inc": g.inc,
                "up": g.unit_price,
                "amt": _money(g.amt),
            },
        )
    audit.record(
        s,
        action="invoice.issued",
        result="success",
        tenant_id=sub["tenant_id"],
        actor_kind="service",
        resource_type="invoice",
        resource_id=str(inv_id),
        metadata={"number": number, "total": str(total), "currency": sub["currency"]},
    )
    emit(
        s,
        sub["tenant_id"],
        "invoice.issued",
        {"invoice_id": str(inv_id), "number": number, "total": str(total), "currency": sub["currency"]},
    )
    return inv_id


def close_due(s: Session, now: datetime | None = None) -> list[UUID]:
    """Closes every ended period of the open subscription: rates it to its end, invoices it and starts the next
    period, applying a pending plan change or cancellation. Then updates past-due status. Idempotent."""
    now = now or datetime.now(UTC)
    issued: list[UUID] = []
    for _ in range(24):  # catches up at most two years of missed periods in one run
        sub = open_subscription(s)
        if sub is None or sub["current_period_end"] > now:
            break
        rate(s, sub, until=sub["current_period_end"])
        inv = issue_invoice(s, sub)
        if inv:
            issued.append(inv)
        start = sub["current_period_end"]
        if sub["cancel_at_period_end"]:
            s.execute(
                text(
                    "update subscriptions set status = 'cancelled', ended_at = :e, cancelled_at = coalesce("
                    "cancelled_at, :e), updated_at = now() where id = :s"
                ),
                {"s": sub["id"], "e": start},
            )
            audit.record(
                s,
                action="subscription.ended",
                result="success",
                tenant_id=sub["tenant_id"],
                actor_kind="service",
                resource_type="subscription",
                resource_id=str(sub["id"]),
            )
            break
        anchor = sub["started_at"].day if sub["trial_ends_at"] is None else sub["trial_ends_at"].day
        s.execute(
            text(
                "update subscriptions set current_period_start = :ps, current_period_end = :pe, "
                "plan_id = coalesce(pending_plan_id, plan_id), pending_plan_id = null, "
                "status = case when status = 'trialing' then 'active' else status end, updated_at = now() "
                "where id = :s"
            ),
            {"s": sub["id"], "ps": start, "pe": add_month(start, anchor)},
        )
        if sub["pending_plan_id"]:
            audit.record(
                s,
                action="subscription.plan_changed",
                result="success",
                tenant_id=sub["tenant_id"],
                actor_kind="service",
                resource_type="subscription",
                resource_id=str(sub["id"]),
                metadata={"plan_id": str(sub["pending_plan_id"])},
            )
        nxt = open_subscription(s)
        assert nxt is not None
        _charge_fee(s, nxt)
    refresh_past_due(s, now)
    return issued


def refresh_past_due(s: Session, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    sub = open_subscription(s)
    if sub is None:
        return
    overdue = s.scalar(
        text("select count(*) from invoices where subscription_id = :s and status = 'open' and due_at < :now"),
        {"s": sub["id"], "now": now},
    )
    if overdue and sub["status"] in ("active", "trialing"):
        s.execute(
            text("update subscriptions set status = 'past_due', updated_at = now() where id = :s"), {"s": sub["id"]}
        )
        audit.record(
            s,
            action="subscription.past_due",
            result="success",
            tenant_id=sub["tenant_id"],
            actor_kind="service",
            resource_type="subscription",
            resource_id=str(sub["id"]),
        )
    elif not overdue and sub["status"] == "past_due":
        trial = sub["trial_ends_at"] is not None and now < sub["trial_ends_at"]
        s.execute(
            text("update subscriptions set status = :st, updated_at = now() where id = :s"),
            {"s": sub["id"], "st": "trialing" if trial else "active"},
        )


def mark_paid(s: Session, invoice_id: UUID, amount: Decimal) -> None:
    s.execute(
        text(
            "update invoices set amount_paid = amount_paid + :a, status = case when amount_paid + :a >= total "
            "then 'paid' else status end, paid_at = case when amount_paid + :a >= total then now() else paid_at end "
            "where id = :i and status = 'open'"
        ),
        {"i": invoice_id, "a": amount},
    )
    refresh_past_due(s)


# ------------------------------------------------------------------ background job
def run_tenant(tenant_id: UUID) -> list[UUID]:
    from ...core.db import session_scope

    with session_scope(tenant_id=tenant_id) as s:
        issued = close_due(s)
        rate(s)
        return issued


def run_all() -> int:
    from ...core.db import session_scope

    with session_scope() as s:
        tenants = [r.tenant_id for r in s.execute(text("select tenant_id from open_subscriptions()")).all()]
    n = 0
    for t in tenants:
        try:
            n += len(run_tenant(t))
        except Exception:  # one organisation's failure never stops the others
            log.exception("billing run failed for a tenant")
    return n


async def loop(interval: float = 300.0) -> None:
    import asyncio

    from starlette.concurrency import run_in_threadpool

    while True:
        try:
            await run_in_threadpool(run_all)
        except Exception:
            log.exception("billing loop failed")
        await asyncio.sleep(interval)
