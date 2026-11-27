# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 7: plans, subscriptions, rating, spending limits, quotas, cost alerts, invoices, test payments, the Super
Admin billing console and analytics. Synthetic plans and prices only; the test payment provider moves no money."""

import json
from decimal import Decimal

import pytest
from sqlalchemy import text

from xplovoice_api.core.config import get_settings
from xplovoice_api.modules.m15_usage import billing, payments

from .conftest import auth, register
from .test_ai import mock_routes
from .test_telephony import number, publish, ring, setup_org, sql, trunk
from .test_tenancy import _mfa_login, invite_and_join
from .test_voice import make_agent

REASON = "Synthetic test plan"


# ------------------------------------------------------------------ helpers
@pytest.fixture
def admin(client, owner_engine):
    staff = register(client, org="Xplosys Ops")
    with owner_engine.begin() as c:
        c.execute(text("update users set is_platform_admin = true where email = :e"), {"e": staff["email"]})
    return _mfa_login(client, staff)


def make_plan(
    client,
    adm,
    *,
    code="growth",
    currency="INR",
    kind="subscription",
    fee="999",
    prices=None,
    activate=True,
    default=False,
    trial_days=0,
    limits=None,
):
    body = {
        "code": code,
        "name": code.title(),
        "kind": kind,
        "currency": currency,
        "trial_days": trial_days,
        "limits": limits or {},
        "prices": ([{"meter": "base_fee", "unit_price": fee}] if fee is not None else []) + (prices or []),
        "reason": REASON,
    }
    r = client.post("/admin/v1/billing/plans", headers=auth(adm), json=body)
    assert r.status_code == 201, r.text
    plan = r.json()
    if activate:
        r = client.post(
            f"/admin/v1/billing/plans/{plan['id']}/status",
            headers=auth(adm),
            json={"status": "active", "is_default": default, "reason": REASON},
        )
        assert r.status_code == 200, r.text
        plan = r.json()
    return plan


def subscribe(client, t, plan):
    r = client.post("/v1/billing/subscription", headers=auth(t), json={"plan_id": plan["id"]})
    assert r.status_code == 200, r.text
    return r.json()


def overview(client, t):
    r = client.get("/v1/billing", headers=auth(t))
    assert r.status_code == 200, r.text
    return r.json()


def usage_of(ov, meter):
    return next((u for u in ov["usage"] if u["meter"] == meter), None)


def phone_call(client, owner_engine, t, n, seconds, caller="+919800000001"):
    cid = ring(client, t, n["e164"], caller=caller)["call_id"]
    client.post(f"/v1/telephony/simulate/calls/{cid}/event", headers=auth(t), json={"status": "in_progress"})
    sql(
        owner_engine,
        "update calls set answered_at = now() - make_interval(secs => :s) where id = :i",
        t["tenant_id"],
        i=cid,
        s=seconds - 3,  # billed seconds round up to the 60-second pulse
    )
    client.post(f"/v1/telephony/simulate/calls/{cid}/event", headers=auth(t), json={"status": "completed"})
    return cid


def end_period(owner_engine, t):
    """Moves the open period into the past, as if the month had ended."""
    sql(
        owner_engine,
        "update subscriptions set current_period_start = current_period_start - interval '31 days', "
        "current_period_end = now() - interval '1 second', started_at = started_at - interval '31 days' "
        "where tenant_id = :t and ended_at is null",
        t["tenant_id"],
        t=t["tenant_id"],
    )
    sql(
        owner_engine,
        "update charge_ledger set period_start = period_start - interval '31 days' where tenant_id = :t",
        t["tenant_id"],
        t=t["tenant_id"],
    )
    with owner_engine.begin() as c:  # prices are append-only for everyone; only the table owner can backdate them
        c.execute(text("alter table plan_prices no force row level security"))
        c.execute(text("update plan_prices set effective_from = effective_from - interval '62 days'"))
        c.execute(text("alter table plan_prices force row level security"))


def run_billing(t):
    return billing.run_tenant(__import__("uuid").UUID(t["tenant_id"]))


def tts(client, t, chars=500):
    """Text-to-speech through the playground, 500 characters per request at most."""
    r = None
    while chars > 0:
        r = client.post("/v1/ai/test/speech", headers=auth(t), json={"text": "a" * min(chars, 500)})
        if r.status_code != 200:
            return r
        chars -= 500
    return r


# ================================================================================================ catalog
def test_no_plans_or_prices_are_seeded_and_only_platform_admins_write_the_catalog(client, owner_engine, admin):
    t = register(client)
    assert client.get("/v1/billing/plans", headers=auth(t)).json() == []
    ov = overview(client, t)
    assert ov["subscription"] is None and ov["blocked"] is None  # no plan: unbilled, nothing refused
    assert {p["key"]: p["status"] for p in ov["payment_providers"]} == {
        "test": "development_only",
        "gateway": "awaiting_configuration",
    }
    assert client.post("/admin/v1/billing/plans", headers=auth(t), json={}).status_code == 403
    # The runtime role cannot write plans or rewrite prices, even with SQL.
    from xplovoice_api.core.db import session_scope

    with pytest.raises(Exception), session_scope(tenant_id=t["tenant_id"]) as s:  # noqa: B017
        s.execute(text("insert into billing_plans (code, name, kind, currency) values ('x1', 'X', 'payg', 'INR')"))
    make_plan(client, admin, activate=False)
    with pytest.raises(Exception), session_scope(tenant_id=t["tenant_id"]) as s:  # noqa: B017
        s.execute(text("update plan_prices set unit_price = 0"))


def test_plan_activation_needs_a_fee_and_prices_are_append_only(client, admin):
    r = client.post(
        "/admin/v1/billing/plans",
        headers=auth(admin),
        json={"code": "nofee", "name": "No fee", "kind": "subscription", "currency": "INR", "reason": REASON},
    )
    bad = client.post(
        f"/admin/v1/billing/plans/{r.json()['id']}/status",
        headers=auth(admin),
        json={"status": "active", "reason": REASON},
    )
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "no_fee"
    payg_fee = client.post(
        "/admin/v1/billing/plans",
        headers=auth(admin),
        json={
            "code": "payg1",
            "name": "P",
            "kind": "payg",
            "currency": "INR",
            "reason": REASON,
            "prices": [{"meter": "base_fee", "unit_price": "10"}],
        },
    )
    assert payg_fee.status_code == 422
    plan = make_plan(client, admin, prices=[{"meter": "phone_inbound_minute", "unit_price": "2"}])
    r = client.post(
        f"/admin/v1/billing/plans/{plan['id']}/prices",
        headers=auth(admin),
        json={"meter": "phone_inbound_minute", "unit_price": "3", "reason": "Price change for test"},
    )
    assert r.status_code == 200
    prices = {p["meter"]: p["unit_price"] for p in r.json()["prices"]}
    assert Decimal(prices["phone_inbound_minute"]) == 3
    with __import__("xplovoice_api.core.db", fromlist=["session_scope"]).session_scope() as s:
        n = s.scalar(text("select count(*) from plan_prices where plan_id = :p"), {"p": plan["id"]})
    assert n == 3  # fee, the first price and the change: nothing rewritten


def test_tenants_see_only_active_plans_in_their_currency(client, admin):
    make_plan(client, admin, code="inr-plan", currency="INR")
    usd = make_plan(client, admin, code="usd-plan", currency="USD", fee="49")
    make_plan(client, admin, code="draft-plan", activate=False)
    india, us = register(client, country="IN"), register(client, country="US")
    assert [p["code"] for p in client.get("/v1/billing/plans", headers=auth(india)).json()] == ["inr-plan"]
    assert [p["code"] for p in client.get("/v1/billing/plans", headers=auth(us)).json()] == ["usd-plan"]
    r = client.post("/v1/billing/subscription", headers=auth(india), json={"plan_id": usd["id"]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "currency_mismatch"


# ================================================================================================ rating
def test_phone_minutes_rated_with_included_minutes_then_invoiced_with_tax(client, owner_engine, admin):
    plan = make_plan(
        client,
        admin,
        prices=[{"meter": "phone_inbound_minute", "unit_price": "2", "included_quantity": "10"}],
    )
    t, a, tr, n = setup_org(client, owner_engine)
    sub = subscribe(client, t, plan)
    assert sub["status"] == "active" and sub["plan"]["code"] == "growth"
    phone_call(client, owner_engine, t, n, 15 * 60)  # 15 minutes: 10 included, 5 at 2.00
    ov = overview(client, t)
    u = usage_of(ov, "phone_inbound_minute")
    assert Decimal(u["quantity"]) == 15 and Decimal(u["included_used"]) == 10 and Decimal(u["amount"]) == 10
    assert Decimal(ov["period_total"]) == Decimal("1009")
    # Tax entered by the platform admin applies to the invoice; none is invented.
    r = client.post(
        "/admin/v1/billing/tax-rates",
        headers=auth(admin),
        json={
            "country_code": "IN",
            "label": "GST (test)",
            "rate_percent": "18",
            "source": "Synthetic test rate",
            "reason": REASON,
        },
    )
    assert r.status_code == 201
    end_period(owner_engine, t)
    issued = run_billing(t)
    assert len(issued) == 1
    assert run_billing(t) == []  # closing again issues nothing
    inv = client.get("/v1/billing/invoices", headers=auth(t)).json()
    assert len(inv) == 1 and inv[0]["number"].startswith("XV-") and inv[0]["status"] == "open"
    d = client.get(f"/v1/billing/invoices/{inv[0]['id']}", headers=auth(t)).json()
    assert [(ln["entry_type"], ln["meter"], Decimal(ln["amount"])) for ln in d["lines"]] == [
        ("fee", "base_fee", Decimal("999.00")),
        ("usage", "phone_inbound_minute", Decimal("10.00")),
    ]
    assert Decimal(d["subtotal"]) == 1009 and Decimal(d["tax_amount"]) == Decimal("181.62")
    assert Decimal(d["total"]) == Decimal("1190.62") and d["tax_label"] == "GST (test)"
    assert d["bill_to"]["name"] == "Acme Clinic" and d["seller"]["name"] == "Xplosys"
    # The next period started with its own fee; nothing carried over.
    ov = overview(client, t)
    assert Decimal(ov["period_total"]) == 999 and usage_of(ov, "phone_inbound_minute")["quantity"] in ("0", 0)


def test_rating_is_idempotent_keeps_the_price_in_force_and_skips_customer_keys(client, owner_engine, admin):
    plan = make_plan(client, admin, fee="0", prices=[{"meter": "tts_1k_characters", "unit_price": "5"}])
    t = register(client)
    mock_routes(client, t, owner_engine)
    subscribe(client, t, plan)
    assert tts(client, t, 2000).status_code == 200
    with __import__("xplovoice_api.core.db", fromlist=["session_scope"]).session_scope(tenant_id=t["tenant_id"]) as s:
        billing.rate(s)
        assert billing.rate(s) == 0  # rating again writes nothing
    client.post(
        f"/admin/v1/billing/plans/{plan['id']}/prices",
        headers=auth(admin),
        json={"meter": "tts_1k_characters", "unit_price": "7", "reason": "Price change for test"},
    )
    assert tts(client, t, 1000).status_code == 200
    # Usage on the customer's own key is the customer's cost: recorded, never charged.
    sql(
        owner_engine,
        "insert into usage_events (tenant_id, idempotency_key, kind, provider_id, model_id, account, unit, quantity, "
        "source_type) select :t, 'customer-key-usage', 'tts', m.provider_id, m.id, 'customer', 'character', 5000, "
        "'playground' from ai_models m where m.model_key = 'mock-tts'",
        t["tenant_id"],
        t=t["tenant_id"],
    )
    ov = overview(client, t)
    u = usage_of(ov, "tts_1k_characters")
    assert Decimal(u["quantity"]) == 3 and Decimal(u["amount"]) == Decimal(2 * 5 + 1 * 7)
    rows = sql(owner_engine, "select count(*) from charge_ledger where entry_type = 'usage'", t["tenant_id"]).scalar()
    assert rows == 6  # one charge per usage event
    # Provider cost is still its own ledger, in the provider's currency.
    cost = sql(owner_engine, "select count(*), min(currency) from provider_cost_ledger", t["tenant_id"]).one()
    assert cost[0] == 6 and cost[1] == "USD"


def test_trial_waives_the_fee_and_ends_into_a_paid_period(client, owner_engine, admin):
    plan = make_plan(client, admin, trial_days=14)
    t = register(client)
    sub = subscribe(client, t, plan)
    assert sub["status"] == "trialing" and sub["trial_ends_at"]
    assert Decimal(overview(client, t)["period_total"]) == 0
    end_period(owner_engine, t)
    run_billing(t)
    ov = overview(client, t)
    assert ov["subscription"]["status"] == "active" and Decimal(ov["period_total"]) == 999
    inv = client.get("/v1/billing/invoices", headers=auth(t)).json()
    assert len(inv) == 1 and Decimal(inv[0]["total"]) == 0 and inv[0]["status"] == "paid"  # nothing due


# ================================================================================================ limits
def test_spending_limit_alerts_once_and_hard_limit_blocks_new_calls(client, owner_engine, admin):
    plan = make_plan(client, admin, fee="900", prices=[{"meter": "tts_1k_characters", "unit_price": "50"}])
    t = register(client)
    mock_routes(client, t, owner_engine)
    agent = make_agent(client, t)
    subscribe(client, t, plan)
    hook = client.post(
        "/v1/integrations/webhooks",
        headers=auth(t),
        json={"name": "Hook", "url": "https://93.184.216.34/hook", "events": ["billing.alert"]},
    )
    assert hook.status_code in (200, 201), hook.text
    r = client.put(
        "/v1/billing/settings", headers=auth(t), json={"spend_limit": "1000", "alert_percents": [50, 80, 100]}
    )
    assert r.status_code == 200
    ov = overview(client, t)
    assert [(a["kind"], a["threshold"]) for a in ov["alerts"]] == [("spend_threshold", 50), ("spend_threshold", 80)]
    assert ov["blocked"] is None
    assert tts(client, t, 2000).status_code == 200  # 900 + 100 = the limit
    ov = overview(client, t)
    assert [a["threshold"] for a in ov["alerts"]] == [50, 80, 100]
    assert ov["blocked"]["code"] == "spend_limit_reached"
    overview(client, t)  # alerts are recorded once per period
    assert sql(owner_engine, "select count(*) from billing_alerts", t["tenant_id"]).scalar() == 3
    events = sql(
        owner_engine, "select count(*) from integration_events where type = 'billing.alert'", t["tenant_id"]
    ).scalar()
    assert events == 3
    r = client.post("/v1/voice/sessions", headers=auth(t), json={"agent_id": agent["id"]})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "spend_limit_reached"
    assert tts(client, t, 10).status_code == 402
    assert client.post(f"/v1/agents/{agent['id']}/chat", headers=auth(t), json={}).status_code == 402
    # A soft limit only alerts.
    client.put("/v1/billing/settings", headers=auth(t), json={"spend_limit": "1000", "hard_limit": False})
    assert overview(client, t)["blocked"] is None and tts(client, t, 10).status_code == 200


def test_quota_blocks_inbound_and_defers_campaign_calls(client, owner_engine, admin):
    plan = make_plan(
        client,
        admin,
        prices=[{"meter": "phone_inbound_minute", "unit_price": "1", "monthly_cap": "5"}],
    )
    t, a, tr, n = setup_org(client, owner_engine)
    subscribe(client, t, plan)
    phone_call(client, owner_engine, t, n, 6 * 60)
    ov = overview(client, t)
    assert ov["blocked"]["code"] == "quota_reached"
    assert [(x["kind"], x["meter"]) for x in ov["alerts"]] == [("quota_reached", "phone_inbound_minute")]
    r = ring(client, t, n["e164"], caller="+919800000002")
    detail = client.get(f"/v1/calls/{r['call_id']}", headers=auth(t)).json()
    assert detail["state"] == "cancelled" and detail["end_reason"] == "billing_quota_reached"
    from xplovoice_api.core.db import session_scope
    from xplovoice_api.modules.m04_telephony import service as tel
    from xplovoice_api.modules.m07_campaigns import policy
    from xplovoice_api.modules.m07_campaigns.models import Campaign, CampaignContact

    c = client.post(
        "/v1/campaigns",
        headers=auth(t),
        json={
            "name": "Reminders",
            "agent_id": a["id"],
            "from_number_id": n["id"],
            "timezone": "Asia/Kolkata",
            "window_start": "00:00",
            "window_end": "23:59",
            "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        },
    )
    assert c.status_code == 201, c.text
    client.post(
        "/v1/consent",
        headers=auth(t),
        json={"phone": "+919800000005", "purpose": "outbound_calls", "status": "granted", "basis": "express_written"},
    )
    client.post(
        f"/v1/campaigns/{c.json()['id']}/contacts",
        headers=auth(t),
        json={"contacts": [{"phone": "+919800000005", "name": "Asha"}]},
    )
    sql(owner_engine, "update campaigns set status = 'running' where id = :i", t["tenant_id"], i=c.json()["id"])
    with session_scope(tenant_id=t["tenant_id"]) as s:
        camp = s.get(Campaign, c.json()["id"])
        contact = s.query(CampaignContact).filter_by(campaign_id=camp.id).one()
        pol = tel.policy_for(s, camp.tenant_id, "IN")
        d = policy.evaluate_outbound(s, pol, camp, contact)
    assert d.decision == "defer" and d.reason == "billing"


def test_plan_limits_on_agents_numbers_and_concurrent_calls(client, owner_engine, admin):
    plan = make_plan(client, admin, limits={"max_agents": 1, "max_phone_numbers": 1, "max_concurrent_calls": 1})
    t = register(client)
    mock_routes(client, t, owner_engine)
    subscribe(client, t, plan)
    a = make_agent(client, t)
    r = client.post("/v1/agents", headers=auth(t), json={"name": "Second"})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "plan_limit"
    tr = trunk(client, t)
    number(client, t, tr, "+918041234567")
    r = client.post("/v1/phone-numbers", headers=auth(t), json={"number": "+918041234568", "trunk_id": tr["id"]})
    assert r.status_code == 402
    publish(owner_engine, a["id"], t["tenant_id"])
    assert client.post("/v1/voice/sessions", headers=auth(t), json={"agent_id": a["id"]}).status_code == 201
    r = client.post("/v1/voice/sessions", headers=auth(t), json={"agent_id": a["id"]})
    assert r.status_code == 429  # the plan allows one live call, below the platform ceiling of two


def test_default_plan_on_registration(client, owner_engine, admin):
    make_plan(client, admin, code="starter", default=True, trial_days=7)
    t = register(client)
    sub = overview(client, t)["subscription"]
    assert sub["plan"]["code"] == "starter" and sub["status"] == "trialing" and sub["source"] == "default_plan"
    assert register(client, country="US") and overview(client, register(client, country="US"))["subscription"] is None


# ================================================================================================ lifecycle
def test_plan_change_and_cancellation_apply_when_the_period_ends(client, owner_engine, admin):
    growth = make_plan(client, admin)
    pro = make_plan(client, admin, code="pro", fee="2999")
    t = register(client)
    subscribe(client, t, growth)
    s = subscribe(client, t, pro)
    assert s["plan"]["code"] == "growth" and s["pending_plan"]["code"] == "pro"
    assert client.post("/v1/billing/subscription", headers=auth(t), json={"plan_id": pro["id"]}).status_code == 409
    end_period(owner_engine, t)
    run_billing(t)
    ov = overview(client, t)
    assert ov["subscription"]["plan"]["code"] == "pro" and Decimal(ov["period_total"]) == 2999
    r = client.post("/v1/billing/subscription/cancel", headers=auth(t))
    assert r.json()["cancel_at_period_end"] is True
    assert client.post("/v1/billing/subscription/resume", headers=auth(t)).json()["cancel_at_period_end"] is False
    client.post("/v1/billing/subscription/cancel", headers=auth(t))
    end_period(owner_engine, t)
    run_billing(t)
    assert overview(client, t)["subscription"] is None
    assert len(client.get("/v1/billing/invoices", headers=auth(t)).json()) == 2
    subscribe(client, t, growth)  # an organisation can start again


# ================================================================================================ payments
def _invoice(client, owner_engine, admin, t=None, plan=None):
    plan = plan or make_plan(client, admin)
    t = t or register(client)
    subscribe(client, t, plan)
    end_period(owner_engine, t)
    run_billing(t)
    return t, client.get("/v1/billing/invoices", headers=auth(t)).json()[0]


def test_test_payment_settles_through_the_signed_webhook_once(client, owner_engine, admin):
    t, inv = _invoice(client, owner_engine, admin)
    r = client.post(f"/v1/billing/invoices/{inv['id']}/pay", headers=auth(t), json={"outcome": "decline"})
    assert r.status_code == 200 and r.json()["status"] == "failed"
    assert client.get(f"/v1/billing/invoices/{inv['id']}", headers=auth(t)).json()["status"] == "open"
    r = client.post(f"/v1/billing/invoices/{inv['id']}/pay", headers=auth(t), json={"outcome": "succeed"})
    assert r.status_code == 200 and r.json()["status"] == "succeeded" and Decimal(r.json()["amount"]) == 999
    d = client.get(f"/v1/billing/invoices/{inv['id']}", headers=auth(t)).json()
    assert d["status"] == "paid" and Decimal(d["amount_paid"]) == 999 and len(d["payments"]) == 2
    assert client.post(f"/v1/billing/invoices/{inv['id']}/pay", headers=auth(t), json={}).status_code == 409
    # A forged or replayed webhook changes nothing.
    ref = sql(owner_engine, "select provider_ref from payments where status = 'succeeded'", t["tenant_id"]).scalar()
    body = json.dumps({"id": "evt_forged", "type": "payment.failed", "payment_ref": ref}).encode()
    bad = client.post("/v1/webhooks/payments/test", content=body, headers={"X-Test-Signature": "t=1,v1=00"})
    assert bad.status_code == 401
    ok = client.post("/v1/webhooks/payments/test", content=body, headers={"X-Test-Signature": payments.sign(body)})
    assert ok.json() == {"result": "ignored"}  # a settled payment is never overturned
    again = client.post("/v1/webhooks/payments/test", content=body, headers={"X-Test-Signature": payments.sign(body)})
    assert again.json() == {"result": "duplicate"}
    events = sql(
        owner_engine, "select count(*) from integration_events where type = 'invoice.paid'", t["tenant_id"]
    ).scalar()
    assert events == 1
    r = client.post(f"/v1/billing/invoices/{inv['id']}/pay", headers=auth(t), json={"provider": "gateway"})
    assert r.status_code in (409, 503)


def test_wrong_amount_in_a_webhook_fails_the_payment(client, owner_engine, admin):
    t, inv = _invoice(client, owner_engine, admin)
    sql(
        owner_engine,
        "insert into payments (tenant_id, invoice_id, provider_key, provider_ref, amount, currency) "
        "values (:t, :i, 'test', 'testpay_manual', 999, 'INR')",
        t["tenant_id"],
        t=t["tenant_id"],
        i=inv["id"],
    )
    body = json.dumps(
        {"id": "evt_1", "type": "payment.succeeded", "payment_ref": "testpay_manual", "amount": "1", "currency": "INR"}
    ).encode()
    r = client.post("/v1/webhooks/payments/test", content=body, headers={"X-Test-Signature": payments.sign(body)})
    assert r.json() == {"result": "applied"}
    assert (
        sql(owner_engine, "select status from payments where provider_ref = 'testpay_manual'", t["tenant_id"]).scalar()
        == "failed"
    )
    assert client.get(f"/v1/billing/invoices/{inv['id']}", headers=auth(t)).json()["status"] == "open"


def test_overdue_invoice_blocks_new_calls_until_paid(client, owner_engine, admin):
    t, inv = _invoice(client, owner_engine, admin)
    sql(owner_engine, "update invoices set due_at = now() - interval '1 day'", t["tenant_id"])
    run_billing(t)
    ov = overview(client, t)
    assert ov["subscription"]["status"] == "past_due" and ov["blocked"]["code"] == "invoice_overdue"
    client.post(f"/v1/billing/invoices/{inv['id']}/pay", headers=auth(t), json={})
    ov = overview(client, t)
    assert ov["subscription"]["status"] == "active" and ov["blocked"] is None


def test_test_payment_provider_is_refused_in_production(client, owner_engine, admin, monkeypatch):
    t, inv = _invoice(client, owner_engine, admin)
    monkeypatch.setattr(get_settings(), "environment", "production")
    r = client.post(f"/v1/billing/invoices/{inv['id']}/pay", headers=auth(t), json={})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "provider_unavailable"
    assert client.post("/v1/webhooks/payments/test", content=b"{}").status_code == 404


# ================================================================================================ access
def test_billing_permissions_isolation_and_append_only_ledger(client, owner_engine, admin):
    t, inv = _invoice(client, owner_engine, admin)
    adm_member = invite_and_join(client, t, "admin")
    viewer = invite_and_join(client, t, "viewer")
    assert client.get("/v1/billing", headers=auth(adm_member)).status_code == 200
    r = client.put("/v1/billing/settings", headers=auth(adm_member), json={"spend_limit": "10"})
    assert r.status_code == 403  # only the owner changes billing
    assert client.get("/v1/billing", headers=auth(viewer)).status_code == 403
    assert client.get("/v1/analytics/overview", headers=auth(viewer)).status_code == 200
    other = register(client, org="Other Org")
    assert client.get(f"/v1/billing/invoices/{inv['id']}", headers=auth(other)).status_code == 404
    assert client.post(f"/v1/billing/invoices/{inv['id']}/pay", headers=auth(other), json={}).status_code == 404
    assert client.get("/v1/billing/ledger", headers=auth(other)).json() == []
    from xplovoice_api.core.db import session_scope

    for stmt in (
        "update charge_ledger set amount = 0",
        "delete from charge_ledger",
        "update invoices set total = 0",
        "delete from invoice_lines",
    ):
        with pytest.raises(Exception), session_scope(tenant_id=t["tenant_id"]) as s:  # noqa: B017
            s.execute(text(stmt))


# ================================================================================================ admin
def test_admin_assigns_credits_voids_and_sees_cost_next_to_charges(client, owner_engine, admin):
    plan = make_plan(client, admin, prices=[{"meter": "tts_1k_characters", "unit_price": "5"}])
    t = register(client)
    mock_routes(client, t, owner_engine)
    r = client.post(
        f"/admin/v1/billing/tenants/{t['tenant_id']}/subscription",
        headers=auth(admin),
        json={"plan_id": plan["id"], "reason": "Signed order form"},
    )
    assert r.status_code == 200 and r.json()["plan"] == "Growth"
    assert overview(client, t)["subscription"]["source"] == "platform_admin"
    tts(client, t, 2000)
    overview(client, t)
    r = client.post(
        f"/admin/v1/billing/tenants/{t['tenant_id']}/credits",
        headers=auth(admin),
        json={"amount": "100", "reason": "Goodwill credit"},
    )
    assert r.status_code == 200 and Decimal(r.json()["period_charges"]) == Decimal(999 + 10 - 100)
    rows = {o["currency"]: o for o in client.get("/admin/v1/billing/overview", headers=auth(admin)).json()}
    inr = rows["INR"]
    assert inr["provider_cost_unconverted"] == ["USD"] and inr["margin_this_month"] is None  # no FX rate entered
    client.post(
        "/admin/v1/billing/fx-rates",
        headers=auth(admin),
        json={"base": "USD", "quote": "INR", "rate": "80", "source": "Synthetic test rate", "reason": REASON},
    )
    inr = {o["currency"]: o for o in client.get("/admin/v1/billing/overview", headers=auth(admin)).json()}["INR"]
    assert inr["active_subscriptions"] == 1 and Decimal(inr["monthly_plan_fees"]) == 999
    assert Decimal(inr["provider_cost_this_month"]) == Decimal("1.6")  # 2,000 mock characters at $0.00001, x80
    assert Decimal(inr["margin_this_month"]) == Decimal(909) - Decimal("1.6")
    r = client.post(
        f"/admin/v1/billing/tenants/{t['tenant_id']}/close-period",
        headers=auth(admin),
        json={"reason": "Close for test"},
    )
    inv_id = r.json()["invoices_issued"][0]
    d = client.get(f"/v1/billing/invoices/{inv_id}", headers=auth(t)).json()
    assert d["lines"][-1]["entry_type"] == "credit" and "Goodwill credit" in d["lines"][-1]["description"]
    assert Decimal(d["total"]) == 909
    v = client.post(
        f"/admin/v1/billing/invoices/{inv_id}/void", headers=auth(admin), json={"reason": "Issued in error"}
    )
    assert v.status_code == 200 and v.json()["status"] == "void"
    with owner_engine.begin() as c:
        c.execute(text("select set_config('app.platform_admin','on',true)"))
        actions = {r[0] for r in c.execute(text("select action from audit_log where actor_kind='platform_admin'"))}
    assert {
        "admin.plan_created",
        "admin.subscription_assigned",
        "admin.credit_issued",
        "admin.invoice_voided",
        "admin.fx_rate_added",
        "admin.period_closed",
    } <= actions
    assert client.get("/admin/v1/billing/subscriptions", headers=auth(t)).status_code == 403


# ================================================================================================ analytics
def test_analytics_counts_calls_outcomes_and_charges(client, owner_engine, admin):
    plan = make_plan(client, admin, prices=[{"meter": "phone_inbound_minute", "unit_price": "2"}])
    t, a, tr, n = setup_org(client, owner_engine)
    subscribe(client, t, plan)
    phone_call(client, owner_engine, t, n, 120)
    phone_call(client, owner_engine, t, n, 60, caller="+919800000003")
    missed = ring(client, t, n["e164"], caller="+919800000004")["call_id"]
    client.post(f"/v1/telephony/simulate/calls/{missed}/event", headers=auth(t), json={"status": "failed"})
    r = client.get("/v1/analytics/overview?days=7", headers=auth(t))
    assert r.status_code == 200, r.text
    body = r.json()
    tot = body["totals"]
    assert tot["calls"] == 3 and tot["completed"] == 2 and tot["failed"] == 1
    assert 2.85 < float(tot["talk_minutes"]) < 3.2 and float(tot["contained_percent"]) == 100.0
    assert body["by_agent"][0]["calls"] == 3 and body["by_channel"] == [{"key": "sip:inbound", "count": 3}]
    assert sum(Decimal(d["charges"]) for d in body["by_day"]) == Decimal(999 + 6)
    viewer = invite_and_join(client, t, "viewer")
    v = client.get("/v1/analytics/overview?days=7", headers=auth(viewer)).json()
    assert v["totals"]["calls"] == 3 and all(d["charges"] is None for d in v["by_day"])  # no money for viewers
    other = register(client, org="Other Org")
    assert client.get("/v1/analytics/overview", headers=auth(other)).json()["totals"]["calls"] == 0
