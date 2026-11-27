# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 6 acceptance: carriers, trunks and numbers; inbound routing, queue and fallback; verified, deduplicated,
order-tolerant carrier webhooks; outbound campaigns behind approval and the policy engine (consent, do-not-call,
calling window, toll-fraud caps); retries; opt-out; transfer; usage in billing pulses; isolation and roles.
Synthetic numbers and the simulated carrier only: no real phone call is placed."""

import asyncio
import base64
import hashlib
import json
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo

import httpx
import jwt
import pytest
from sqlalchemy import create_engine, text

from xplovoice_api.core.config import get_settings
from xplovoice_api.core.db import session_scope
from xplovoice_api.modules.m04_telephony.adapters import livekit_sip, simulated
from xplovoice_api.modules.m04_telephony.adapters.base import PlaceRequest, TrunkSpec, outcome_for_sip_status
from xplovoice_api.modules.m06_inbound import service as inbound
from xplovoice_api.modules.m07_campaigns import dialer, policy
from xplovoice_api.modules.m07_campaigns.models import Campaign

from .conftest import auth, register
from .test_ai import mock_routes
from .test_tenancy import invite_and_join
from .test_voice import WK, job_token, make_agent

FULL_DAY = {"start": "00:00", "end": "23:59"}
ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
OK, BUSY, NO_ANSWER, FAILS = "+919812345671", "+919812345672", "+919812345673", "+919812345674"


@pytest.fixture(autouse=True)
def _open_windows(monkeypatch):
    # The country windows are tested on their own (test_calling_window); elsewhere, any time of day may dial.
    monkeypatch.setitem(policy.COUNTRY_WINDOWS, "IN", (dtime(0, 0), dtime(23, 59)))
    monkeypatch.setitem(policy.COUNTRY_WINDOWS, "US", (dtime(0, 0), dtime(23, 59)))
    livekit_sip._transport = None
    yield
    livekit_sip._transport = None


@pytest.fixture
def redis_client():
    from xplovoice_api.core.ratelimit import client

    return client()


def sql(owner_engine, q, tenant=None, **p):
    """As the table owner, inside one organisation's RLS context (tenant rows) or as the platform (audit)."""
    with owner_engine.begin() as c:
        c.execute(text("select set_config('app.platform_admin', 'on', true)"))
        c.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant or "")})
        return c.execute(text(q), p)


def publish(owner_engine, agent_id, tenant):
    sql(
        owner_engine,
        "update agents set status = 'published', published_version_id = current_version_id where id = :a",
        tenant,
        a=agent_id,
    )


def run(coro):
    return asyncio.run(coro)


async def _tick():
    return await asyncio.gather(*await dialer.tick())


def trunk(client, t, **kw):
    r = client.post(
        "/v1/telephony/trunks", headers=auth(t), json={"name": "Office line", "provider_key": "simulated"} | kw
    )
    assert r.status_code == 201, r.text
    return r.json()


def number(client, t, tr, e164, **kw):
    r = client.post("/v1/phone-numbers", headers=auth(t), json={"number": e164, "trunk_id": tr["id"]} | kw)
    assert r.status_code == 201, r.text
    return r.json()


def setup_org(client, owner_engine, *, country="IN", dial="+918041234567", agent_cfg=None):
    t = register(client, country=country)
    mock_routes(client, t, owner_engine)
    a = make_agent(client, t, **(agent_cfg or {}))
    publish(owner_engine, a["id"], t["tenant_id"])
    tr = trunk(client, t)
    n = number(client, t, tr, dial)
    r = client.put(f"/v1/phone-numbers/{n['id']}/route", headers=auth(t), json={"agent_id": a["id"]})
    assert r.status_code == 200, r.text
    return t, a, tr, r.json()


def ring(client, t, to, caller="+919800000001"):
    r = client.post("/v1/telephony/simulate/inbound", headers=auth(t), json={"to": to, "caller": caller})
    assert r.status_code == 200, r.text
    return r.json()


def call(client, t, call_id):
    r = client.get(f"/v1/calls/{call_id}", headers=auth(t))
    assert r.status_code == 200, r.text
    return r.json()


def carrier_post(client, body: bytes, sig: str | None = None):
    return client.post(
        "/v1/webhooks/telephony/simulated",
        content=body,
        headers={"X-Carrier-Signature": sig if sig is not None else simulated.sign(body)},
    )


def sim_event(ref, status, ev_id=None):
    b = json.loads(simulated.event(ref, status))
    if ev_id:
        b["id"] = ev_id
    return json.dumps(b).encode()


# ================================================================================================ M04 numbers
def test_trunks_and_numbers_keep_secrets_and_numbers_unique(client, owner_engine):
    t = register(client)
    names = {p["key"]: p["status"] for p in client.get("/v1/telephony/providers", headers=auth(t)).json()}
    assert names == {"managed": "awaiting_configuration", "simulated": "development_only", "sip": "available"}
    tr = trunk(client, t, auth_username="acme", auth_password="s3cret-trunk-pass", billing_pulse_seconds=30)
    assert tr["has_password"] is True and "s3cret" not in json.dumps(tr) and tr["sync_status"] == "not_required"
    stored = sql(
        owner_engine, "select auth_secret_ciphertext from sip_trunks where id = :i", t["tenant_id"], i=tr["id"]
    ).scalar()
    assert stored and "s3cret" not in stored
    n = number(client, t, tr, "080 4123 4567")
    assert n["e164"] == "+918041234567" and n["country_code"] == "IN"
    assert (
        client.post("/v1/phone-numbers", headers=auth(t), json={"number": "1234", "trunk_id": tr["id"]}).json()[
            "detail"
        ]["code"]
        == "invalid_phone"
    )
    # A number belongs to one organisation at a time, and nobody learns which one has it.
    other = register(client, org="Other Org")
    r = client.post(
        "/v1/phone-numbers",
        headers=auth(other),
        json={"number": "+918041234567", "trunk_id": trunk(client, other)["id"]},
    )
    assert r.status_code == 409 and "Acme" not in r.text
    # A SIP trunk that places calls needs the carrier's address.
    r = client.post("/v1/telephony/trunks", headers=auth(t), json={"name": "x", "provider_key": "sip"})
    assert r.json()["detail"]["code"] == "address_required"


def test_roles_for_telephony(client, owner_engine):
    t, a, tr, n = setup_org(client, owner_engine)
    viewer = invite_and_join(client, t, "viewer")
    operator = invite_and_join(client, t, "operator")
    assert client.get("/v1/phone-numbers", headers=auth(viewer)).status_code == 200
    assert client.post("/v1/queues", headers=auth(viewer), json={"name": "q"}).status_code == 403
    assert (
        client.put(
            "/v1/destination-policy",
            headers=auth(operator),
            json={
                "telephony_enabled": False,
                "allowed_countries": ["IN"],
                "max_concurrent_outbound": 2,
                "daily_outbound_minutes": 10,
            },
        ).status_code
        == 403
    )
    assert client.post("/v1/suppression", headers=auth(operator), json={"phone": OK}).status_code == 201
    assert client.post("/v1/campaigns", headers=auth(operator), json={}).status_code == 403


# ================================================================================================ M06 inbound
def test_inbound_routes_queues_and_falls_back(client, owner_engine, redis_client):
    t, a, tr, n = setup_org(client, owner_engine)
    first = ring(client, t, n["e164"])
    assert first["result"] == "dispatched"
    c = call(client, t, first["call_id"])
    assert (c["channel"], c["direction"], c["status"], c["state"]) == ("sip", "inbound", "dispatching", "routing")
    assert c["from_number"] == "+919800000001" and c["to_number"] == n["e164"]
    assert job_token(redis_client, first["call_id"])
    second = ring(client, t, n["e164"])
    assert second["result"] == "dispatched", second  # the organisation's limit is 2 calls
    # Limit reached, no queue: the fallback message (a worker says it and hangs up).
    fb = ring(client, t, n["e164"])
    assert fb["result"] == "fallback"
    assert call(client, t, fb["call_id"])["status"] == "dispatching"
    with session_scope(tenant_id=uuid.UUID(t["tenant_id"])) as s:
        from xplovoice_api.modules.m08_calls.models import Call

        assert s.get(Call, uuid.UUID(fb["call_id"])).options["fallback_message"]
    # With a queue the caller waits, and is connected as soon as a call ends.
    q = client.post(
        "/v1/queues", headers=auth(t), json={"name": "Reception", "max_waiting": 1, "max_wait_seconds": 30}
    ).json()
    client.put(f"/v1/phone-numbers/{n['id']}/route", headers=auth(t), json={"agent_id": a["id"], "queue_id": q["id"]})
    for cid in (first["call_id"], fb["call_id"]):
        client.post(f"/v1/telephony/simulate/calls/{cid}/event", headers=auth(t), json={"status": "completed"})
    third = ring(client, t, n["e164"])
    assert third["result"] == "dispatched"  # a slot was free
    waiting = ring(client, t, n["e164"])
    assert waiting["result"] == "queued"
    assert call(client, t, waiting["call_id"])["state"] == "queued"
    assert client.get("/v1/queues", headers=auth(t)).json()[0]["waiting"] == 1
    full = ring(client, t, n["e164"])
    assert full["result"] == "fallback"  # the queue is full (max 1 waiting)
    assert run(inbound.queue_tick()) == 0  # still no slot
    for cid in (third["call_id"], full["call_id"]):  # the fallback message used a worker too
        client.post(f"/v1/telephony/simulate/calls/{cid}/event", headers=auth(t), json={"status": "completed"})
    assert run(inbound.queue_tick()) == 1
    c = call(client, t, waiting["call_id"])
    assert c["state"] == "routing" and c["status"] == "dispatching"
    assert [x["to_state"] for x in c["transitions"]] == ["queued", "routing"]


def test_queue_times_out_to_fallback_and_hangup(client, owner_engine):
    t, a, tr, n = setup_org(client, owner_engine)
    q = client.post("/v1/queues", headers=auth(t), json={"name": "Q", "max_wait_seconds": 10}).json()
    client.put(
        f"/v1/phone-numbers/{n['id']}/route",
        headers=auth(t),
        json={"agent_id": a["id"], "queue_id": q["id"], "fallback_action": "hangup"},
    )
    ring(client, t, n["e164"])
    ring(client, t, n["e164"])
    w = ring(client, t, n["e164"])
    assert w["result"] == "queued"
    sql(
        owner_engine,
        "update calls set queued_at = now() - interval '11 seconds' where id = :i",
        t["tenant_id"],
        i=w["call_id"],
    )
    assert run(inbound.queue_tick()) == 1
    c = call(client, t, w["call_id"])
    assert c["state"] == "cancelled" and c["end_reason"] == "queue_timeout" and c["status"] == "abandoned"


def test_inbound_unknown_unpublished_and_paused(client, owner_engine):
    t, a, tr, n = setup_org(client, owner_engine)
    assert ring(client, t, n["e164"])["result"] == "dispatched"
    assert (
        run(inbound.route_inbound(room="xvin_x1", dialled="+918049999999", caller=None, provider="simulated")).result
        == "unknown_number"
    )
    sql(owner_engine, "update agents set status = 'paused' where id = :a", t["tenant_id"], a=a["id"])
    r = ring(client, t, n["e164"])
    assert r["result"] == "fallback" and r["reason"] == "unavailable"
    publish(owner_engine, a["id"], t["tenant_id"])
    pol = client.get("/v1/destination-policy", headers=auth(t)).json()
    pol["telephony_enabled"] = False
    assert client.put("/v1/destination-policy", headers=auth(t), json=pol).status_code == 200
    r = ring(client, t, n["e164"])
    assert r["result"] == "hangup" and call(client, t, r["call_id"])["end_reason"] == "telephony_disabled"
    acts = [x[0] for x in sql(owner_engine, "select action from audit_log where tenant_id = :t", t=t["tenant_id"])]
    assert "telephony.paused" in acts


def test_inbound_calls_stay_in_their_organisation(client, owner_engine):
    t, a, tr, n = setup_org(client, owner_engine)
    other, oa, otr, on = setup_org(client, owner_engine, dial="+918041230000")
    mine = ring(client, t, n["e164"])
    theirs = ring(client, other, on["e164"])
    assert call(client, other, theirs["call_id"])["to_number"] == on["e164"]
    assert client.get(f"/v1/calls/{mine['call_id']}", headers=auth(other)).status_code == 404
    assert [c["id"] for c in client.get("/v1/calls", headers=auth(other)).json()] == [theirs["call_id"]]
    # One organisation can't ring another organisation's number through its own simulator.
    r = client.post("/v1/telephony/simulate/inbound", headers=auth(other), json={"to": n["e164"]})
    assert r.status_code == 422
    app = create_engine(os.environ["XV_DATABASE_URL"])  # the runtime role, RLS enforced
    with app.connect() as c:
        c.execute(text("select set_config('app.tenant_id', :t, false)"), {"t": other["tenant_id"]})
        for table in ("phone_numbers", "sip_trunks", "call_provider_refs", "call_state_transitions", "inbound_routes"):
            rows = c.execute(text(f"select count(*) from {table} where tenant_id = :t"), {"t": t["tenant_id"]})  # noqa: S608
            assert rows.scalar() == 0, table
            mine = c.execute(text(f"select count(*) from {table} where tenant_id = :t"), {"t": other["tenant_id"]})  # noqa: S608
            assert mine.scalar() >= 1, table
    app.dispose()


# ================================================================================================ webhooks
def test_carrier_webhooks_are_verified_deduplicated_and_order_tolerant(client, owner_engine):
    t, a, tr, n = setup_org(client, owner_engine)
    cid = ring(client, t, n["e164"])["call_id"]
    ref = f"simcall_{cid}"
    body = sim_event(ref, "in_progress", "ev-1")
    assert carrier_post(client, body, "t=1,v1=bad").status_code == 401
    old = int(time.time()) - 3600
    assert carrier_post(client, body, simulated.sign(body, old)).status_code == 401  # replay outside the window
    tampered = body.replace(b"in_progress", b"completed")
    assert carrier_post(client, tampered, simulated.sign(body)).status_code == 401
    assert carrier_post(client, body).json()["result"] == "applied"
    assert carrier_post(client, body).json()["result"] == "duplicate"  # the same event delivered twice
    assert carrier_post(client, sim_event(ref, "completed", "ev-2")).json()["result"] == "applied"
    late = carrier_post(client, sim_event(ref, "in_progress", "ev-3")).json()  # arrives after the end
    assert late["result"] == "ignored"
    c = call(client, t, cid)
    assert c["state"] == "completed" and c["status"] == "completed"
    assert [(e["state"], e["applied"]) for e in c["carrier_events"]] == [
        ("in_progress", True),
        ("completed", True),
        ("in_progress", False),
    ]
    assert [x["to_state"] for x in c["transitions"]][-2:] == ["in_progress", "completed"]
    assert carrier_post(client, sim_event("simcall_nobody", "completed")).json()["result"] == "unknown_call"
    assert client.post("/v1/webhooks/telephony/othercarrier", content=b"{}").status_code == 404


def lk_sign(body: bytes, secret=None) -> str:
    s = get_settings()
    claims = {
        "iss": s.livekit_api_key,
        "sha256": base64.b64encode(hashlib.sha256(body).digest()).decode(),
        "exp": int(time.time()) + 60,
    }
    return "Bearer " + jwt.encode(claims, secret or s.livekit_api_secret, algorithm="HS256")


def test_livekit_webhook_routes_sip_callers_and_ends_calls(client, owner_engine):
    t, a, tr, n = setup_org(client, owner_engine)
    room = "xvin_" + uuid.uuid4().hex
    joined = json.dumps(
        {
            "event": "participant_joined",
            "id": "EV_1",
            "createdAt": time.time(),
            "room": {"name": room},
            "participant": {
                "identity": "sip_919800000002",
                "kind": "SIP",
                "attributes": {
                    "sip.trunkPhoneNumber": n["e164"],
                    "sip.phoneNumber": "+919800000002",
                    "sip.callID": "SCL_1",
                },
            },
        }
    ).encode()

    def post(b, sig=None):
        return client.post(
            "/v1/webhooks/livekit",
            content=b,
            headers={"Authorization": sig or lk_sign(b)},
        )

    assert post(joined, lk_sign(joined, "x" * 40)).status_code == 401
    assert post(joined, lk_sign(b"other body")).status_code == 401
    assert post(joined).json()["result"] == "dispatched"
    assert post(joined).json()["result"] == "duplicate"  # LiveKit retried: routed once
    calls = client.get("/v1/calls", headers=auth(t)).json()
    assert len(calls) == 1 and calls[0]["from_number"] == "+919800000002"
    left = json.dumps(
        {
            "event": "participant_left",
            "id": "EV_2",
            "room": {"name": room},
            "participant": {"identity": "sip_919800000002", "kind": "SIP"},
        }
    ).encode()
    assert post(left).json()["result"] == "applied"
    assert post(left).json()["result"] == "duplicate"
    c = call(client, t, calls[0]["id"])
    assert c["state"] == "disconnected" and c["end_reason"] == "caller_hangup"
    browser = json.dumps({"event": "room_finished", "id": "EV_3", "room": {"name": "call_abc"}}).encode()
    assert post(browser).json()["result"] == "ignored"  # browser test calls end through the worker


# ================================================================================================ M07 campaigns
def campaign(client, t, a, n, **kw):
    body = {
        "name": "Reminders",
        "agent_id": a["id"],
        "from_number_id": n["id"],
        "timezone": "Asia/Kolkata",
        "window_start": FULL_DAY["start"],
        "window_end": FULL_DAY["end"],
        "days": ALL_DAYS,
    } | kw
    r = client.post("/v1/campaigns", headers=auth(t), json=body)
    assert r.status_code == 201, r.text
    return r.json()


def add(client, t, c, phones, basis="express_written"):
    r = client.post(
        f"/v1/campaigns/{c['id']}/contacts",
        headers=auth(t),
        json={"contacts": [{"phone": p} for p in phones], "consent_basis": basis},
    )
    assert r.status_code == 200, r.text
    return r.json()


def go(client, t, c):
    assert client.post(f"/v1/campaigns/{c['id']}/approve", headers=auth(t)).status_code == 200
    r = client.post(f"/v1/campaigns/{c['id']}/start", headers=auth(t))
    assert r.status_code == 200, r.text


def contacts(client, t, c):
    return {k["phone"]: k for k in client.get(f"/v1/campaigns/{c['id']}/contacts", headers=auth(t)).json()}


def test_sole_approver_may_approve_own_campaign_and_it_is_labelled(client, owner_engine):
    t, a, tr, n = setup_org(client, owner_engine)
    c = campaign(client, t, a, n)
    add(client, t, c, [OK])
    r = client.post(f"/v1/campaigns/{c['id']}/approve", headers=auth(t))
    assert r.status_code == 200 and r.json()["self_approved"] is True


def test_campaigns_need_approval_by_another_person(client, owner_engine):
    t, a, tr, n = setup_org(client, owner_engine)
    c = campaign(client, t, a, n)
    assert client.post(f"/v1/campaigns/{c['id']}/start", headers=auth(t)).json()["detail"]["code"] == "not_approved"
    assert client.post(f"/v1/campaigns/{c['id']}/approve", headers=auth(t)).json()["detail"]["code"] == "no_contacts"
    add(client, t, c, [OK])
    admin = invite_and_join(client, t, "admin")
    assert client.post(f"/v1/campaigns/{c['id']}/approve", headers=auth(t)).status_code == 403  # own campaign
    designer = invite_and_join(client, t, "agent_designer")
    assert client.post(f"/v1/campaigns/{c['id']}/approve", headers=auth(designer)).status_code == 403
    r = client.post(f"/v1/campaigns/{c['id']}/approve", headers=auth(admin))
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["self_approved"] is False
    # Any change sends it back for approval.
    body = {
        k: r.json()[k] for k in ("name", "agent_id", "from_number_id", "timezone", "window_start", "window_end", "days")
    } | {"max_attempts": 3}
    assert client.put(f"/v1/campaigns/{c['id']}", headers=auth(t), json=body).json()["status"] == "draft"
    client.post(f"/v1/campaigns/{c['id']}/approve", headers=auth(admin))
    assert client.post(f"/v1/campaigns/{c['id']}/start", headers=auth(t)).json()["status"] == "running"
    assert client.put(f"/v1/campaigns/{c['id']}", headers=auth(t), json=body).status_code == 409  # pause first
    acts = [x[0] for x in sql(owner_engine, "select action from audit_log where tenant_id = :t", t=t["tenant_id"])]
    assert {"campaign.created", "campaign.approved", "campaign.started", "campaign.contacts_imported"} <= set(acts)


def test_consent_and_do_not_call_block_before_any_carrier_request(client, owner_engine, monkeypatch):
    t, a, tr, n = setup_org(client, owner_engine)
    placed = []
    real = simulated.SimulatedCarrier.place_call

    async def spy(self, req):
        placed.append(req.to_e164)
        return await real(self, req)

    monkeypatch.setattr(simulated.SimulatedCarrier, "place_call", spy)
    no_consent, on_dnc, foreign = "+919812345675", "+919812345676", "+14155552671"
    client.post("/v1/suppression", headers=auth(t), json={"phone": on_dnc, "reason": "complaint"})
    c = campaign(client, t, a, n)
    add(client, t, c, [OK, on_dnc, foreign])  # consent recorded for these (not for a number on the list)
    r = client.post(
        f"/v1/campaigns/{c['id']}/contacts",
        headers=auth(t),
        json={"contacts": [{"phone": no_consent}, {"phone": "12"}]},
    )
    assert r.json()["added"] == 1 and r.json()["invalid"][0]["reason"] == "invalid_phone"
    go(client, t, c)
    outcomes = run(_tick())
    assert outcomes == ["answered"] and placed == [OK]  # nobody else reached the carrier
    k = contacts(client, t, c)
    assert k[OK]["status"] == "calling" and k[OK]["attempts"] == 1
    assert (k[no_consent]["status"], k[no_consent]["block_reason"]) == ("blocked", "no_consent")
    assert (k[on_dnc]["status"], k[on_dnc]["block_reason"]) == ("blocked", "do_not_call")
    assert (k[foreign]["status"], k[foreign]["block_reason"]) == ("blocked", "country_allowed")
    decisions = client.get(f"/v1/campaigns/{c['id']}/decisions", headers=auth(t)).json()
    by_phone = {d["phone"]: d for d in decisions}
    assert by_phone[OK]["decision"] == "allow" and all(x["ok"] for x in by_phone[OK]["checks"])
    assert by_phone[no_consent]["checks"][-1] == {
        "check": "consent",
        "ok": False,
        "detail": "No recorded consent to be called.",
    }
    cl = call(client, t, k[OK]["last_call_id"])
    assert (cl["direction"], cl["state"], cl["to_number"]) == ("outbound", "connected", OK)
    # The call ends: the contact is completed and the campaign, with nothing left to dial, too.
    client.post(f"/v1/telephony/simulate/calls/{cl['id']}/event", headers=auth(t), json={"status": "completed"})
    assert contacts(client, t, c)[OK]["status"] == "completed"
    assert client.get(f"/v1/campaigns/{c['id']}", headers=auth(t)).json()["status"] == "completed"
    # Consent granted after the person was put on the list is refused; revoked consent blocks.
    assert (
        client.post("/v1/consent", headers=auth(t), json={"phone": on_dnc, "basis": "express_verbal"}).status_code
        == 409
    )
    client.post("/v1/consent/revoke", headers=auth(t), json={"phone": OK, "reason": "Asked by email"})
    with session_scope(tenant_id=uuid.UUID(t["tenant_id"])) as s:
        from xplovoice_api.modules.m22_consent.service import has_consent

        assert has_consent(s, OK, "outbound_calls") is False and has_consent(s, foreign, "outbound_calls") is True


def test_retry_then_exhausted_and_carrier_outcomes(client, owner_engine):
    t, a, tr, n = setup_org(client, owner_engine)
    c = campaign(client, t, a, n, max_attempts=2, retry_minutes=15, max_concurrent=5, calls_per_minute=10)
    add(client, t, c, [BUSY, NO_ANSWER, FAILS])
    go(client, t, c)
    assert sorted(run(_tick())) == ["busy", "failed", "no_answer"]
    k = contacts(client, t, c)
    for p, outcome in ((BUSY, "busy"), (NO_ANSWER, "no_answer"), (FAILS, "failed")):
        assert (k[p]["status"], k[p]["last_outcome"], k[p]["attempts"]) == ("retry", outcome, 1)
        wait = datetime.fromisoformat(k[p]["next_attempt_at"]) - datetime.now(UTC)
        assert timedelta(minutes=14) < wait <= timedelta(minutes=15)
    assert run(_tick()) == []  # not due yet
    sql(
        owner_engine,
        "update campaign_contacts set next_attempt_at = now() where campaign_id = :c",
        t["tenant_id"],
        c=c["id"],
    )
    assert len(run(_tick())) == 3
    k = contacts(client, t, c)
    assert {v["status"] for v in k.values()} == {"exhausted"} and {v["attempts"] for v in k.values()} == {2}
    busy_call = call(client, t, k[BUSY]["last_call_id"])
    assert busy_call["state"] == "busy" and busy_call["end_reason"] == "busy"
    attempts = client.get(f"/v1/campaigns/{c['id']}/attempts", headers=auth(t)).json()
    assert len(attempts) == 6 and {x["sip_status"] for x in attempts} == {486, 480, 503}
    assert client.get(f"/v1/campaigns/{c['id']}", headers=auth(t)).json()["status"] == "completed"
    # Nothing was answered, so nothing is billed.
    assert sql(owner_engine, "select count(*) from telephony_usage", t["tenant_id"]).scalar() == 0


def test_toll_fraud_caps(client, owner_engine):
    t, a, tr, n = setup_org(client, owner_engine, country="US", dial="+14155550100")
    c = campaign(client, t, a, n, timezone="America/Los_Angeles", max_concurrent=1, calls_per_minute=1)
    premium = "+19005552671"
    add(client, t, c, [premium, "+14155552671", "+14155552672", "+14155552673"])
    go(client, t, c)
    # Premium-rate numbers are blocked even though the country is allowed.
    run(_tick())
    k = contacts(client, t, c)
    assert k[premium]["block_reason"] == "not_premium"
    dialled = [p for p, v in k.items() if v["status"] == "calling"]
    assert len(dialled) == 1  # the campaign's limit of one call at a time
    reasons = {d["reason"] for d in client.get(f"/v1/campaigns/{c['id']}/decisions", headers=auth(t)).json()}
    assert "campaign_concurrency" in reasons
    tid = uuid.UUID(t["tenant_id"])

    def decide(**pol):
        with session_scope(tenant_id=tid) as s:
            from xplovoice_api.modules.m04_telephony.service import policy_for
            from xplovoice_api.modules.m07_campaigns.models import CampaignContact

            p = policy_for(s, tid, "US")
            for key, v in pol.items():
                setattr(p, key, v)
            camp = s.get(Campaign, uuid.UUID(c["id"]))
            camp.max_concurrent, camp.calls_per_minute = 10, 30
            contact = s.get(CampaignContact, uuid.UUID(k["+14155552673"]["id"]))
            d = policy.evaluate_outbound(s, p, camp, contact)
            s.rollback()
            return d.decision, d.reason

    assert decide() == ("allow", None)
    assert decide(telephony_enabled=False) == ("block", "organisation_enabled")
    assert decide(allowed_countries=["IN"]) == ("block", "country_allowed")
    assert decide(max_concurrent_outbound=1) == ("defer", "organisation_concurrency")
    sql(
        owner_engine,
        "insert into telephony_usage (tenant_id, call_id, provider_key, direction, connected_seconds, "
        "pulse_seconds, billed_seconds) values (:tid, :c, 'simulated', 'outbound', 600, 60, 600)",
        t["tenant_id"],
        tid=t["tenant_id"],
        c=k[dialled[0]]["last_call_id"],
    )
    assert decide(daily_outbound_minutes=10) == ("defer", "daily_minutes")
    get_settings().telephony_enabled = False
    try:
        assert decide() == ("block", "platform_enabled")
    finally:
        get_settings().telephony_enabled = True


def test_calling_window_in_the_persons_local_time(client, owner_engine, monkeypatch):
    monkeypatch.setitem(policy.COUNTRY_WINDOWS, "IN", (dtime(9, 0), dtime(21, 0)))
    camp = Campaign(
        window_start=dtime(8, 0),
        window_end=dtime(22, 0),
        days=["mon", "tue", "wed", "thu", "fri"],
        timezone="Asia/Kolkata",
    )
    ist = ZoneInfo("Asia/Kolkata")
    monday = datetime(2026, 11, 23, tzinfo=ist)
    at = lambda h, m=0, d=monday: d.replace(hour=h, minute=m).astimezone(UTC)  # noqa: E731
    assert not policy.window_open(camp, OK, None, at(8, 30))  # campaign allows 08:00, the country default 09:00
    assert policy.window_open(camp, OK, None, at(9, 0))
    assert not policy.window_open(camp, OK, None, at(21, 0))
    assert not policy.window_open(camp, OK, None, at(12, 0, monday + timedelta(days=5)))  # Saturday
    assert policy.next_window(camp, OK, None, at(21, 30)) == at(9, 0, monday + timedelta(days=1))
    # A contact's own time zone wins: 10:00 in India is 23:30 the night before in New York.
    assert not policy.window_open(camp, OK, "America/New_York", at(10, 0))
    # A number that may be in several zones must be inside the window in all of them.
    us = Campaign(window_start=dtime(8, 0), window_end=dtime(21, 0), days=ALL_DAYS, timezone="America/New_York")
    monkeypatch.setitem(policy.COUNTRY_WINDOWS, "US", (dtime(8, 0), dtime(21, 0)))
    multi = "+19005552671"
    assert len(policy.recipient_zones(multi, None, "America/New_York")) > 1
    noon_ny = datetime(2026, 11, 23, 12, 0, tzinfo=ZoneInfo("America/New_York"))
    assert policy.window_open(us, "+12125552672", None, noon_ny)
    assert not policy.window_open(us, multi, None, noon_ny)  # still night in Guam


def test_window_defers_and_no_window_blocks(client, owner_engine, monkeypatch):
    t, a, tr, n = setup_org(client, owner_engine)
    c = campaign(client, t, a, n)
    add(client, t, c, [OK])
    go(client, t, c)
    monkeypatch.setattr(policy, "window_open", lambda *a, **k: False)
    monkeypatch.setattr(policy, "next_window", lambda *a, **k: datetime.now(UTC) + timedelta(hours=3))
    assert run(_tick()) == []
    k = contacts(client, t, c)[OK]
    assert k["status"] == "pending" and datetime.fromisoformat(k["next_attempt_at"]) > datetime.now(UTC)
    monkeypatch.setattr(policy, "next_window", lambda *a, **k: None)
    sql(
        owner_engine,
        "update campaign_contacts set next_attempt_at = now() where campaign_id = :c",
        t["tenant_id"],
        c=c["id"],
    )
    run(_tick())
    k = contacts(client, t, c)[OK]
    assert (k["status"], k["block_reason"]) == ("blocked", "calling_window")


def worker(redis_client, call_id):
    return {**WK, "Authorization": f"Bearer {job_token(redis_client, call_id)}"}


def test_opt_out_on_a_call_stops_every_campaign(client, owner_engine, redis_client):
    t, a, tr, n = setup_org(client, owner_engine)
    c1, c2 = campaign(client, t, a, n), campaign(client, t, a, n, name="Second")
    add(client, t, c1, [OK])
    add(client, t, c2, [OK])
    go(client, t, c1)
    run(_tick())
    cid = contacts(client, t, c1)[OK]["last_call_id"]
    h = worker(redis_client, cid)
    boot = client.post(f"/internal/v1/calls/{cid}/bootstrap", headers=h, json={"worker_id": "w1"}).json()
    assert OK not in json.dumps(boot["config"]["telephony"]) and boot["config"]["telephony"]["opt_out_phrases"]
    r = client.post(f"/internal/v1/calls/{cid}/opt-out", headers=h, json={"said": "please stop calling me"})
    assert r.status_code == 200
    assert contacts(client, t, c1)[OK]["status"] == "opted_out" and contacts(client, t, c2)[OK]["status"] == "opted_out"
    entry = client.get("/v1/suppression", headers=auth(t)).json()[0]
    assert (entry["phone"], entry["reason"], entry["source"], entry["call_id"]) == (OK, "opt_out", "call", cid)
    assert client.get("/v1/consent", headers=auth(t), params={"phone": OK}).json()[0]["status"] == "revoked"
    # Taking the number off the list needs approve rights and, after an opt-out, a real reason.
    designer = invite_and_join(client, t, "operator")
    rm = f"/v1/suppression/{entry['id']}/remove"
    assert client.post(rm, headers=auth(designer), json={"reason": "asked again"}).status_code == 403
    assert client.post(rm, headers=auth(t), json={"reason": "ok"}).json()["detail"]["code"] == "reason_required"
    r = client.post(rm, headers=auth(t), json={"reason": "Customer called us and asked to be called back"})
    assert r.status_code == 200 and r.json()["removed_at"]
    assert client.get("/v1/suppression", headers=auth(t), params={"include_removed": True}).json()[0]["removed_reason"]


def test_transfer_success_failure_and_destination_rules(client, owner_engine, redis_client):
    targets = [
        {"label": "Front desk", "number": "+919812345678"},
        {"label": "Broken line", "number": "+919812345679"},
        {"label": "Abroad", "number": "+14155552671"},
    ]
    t, a, tr, n = setup_org(client, owner_engine, agent_cfg={"transfer": {"enabled": True, "targets": targets}})
    ok_call = ring(client, t, n["e164"])["call_id"]
    h = worker(redis_client, ok_call)
    boot = client.post(f"/internal/v1/calls/{ok_call}/bootstrap", headers=h, json={"worker_id": "w1"}).json()
    tel = boot["config"]["telephony"]
    assert tel["can_transfer"] and tel["transfer_targets"] == ["Front desk", "Broken line", "Abroad"]
    assert "+9198123" not in json.dumps(tel)  # numbers never leave the server
    client.post(f"/internal/v1/calls/{ok_call}/state", headers=h, json={"status": "active"})
    assert client.post(f"/internal/v1/calls/{ok_call}/transfer", headers=h, json={"target": 0}).json()["ok"] is True
    c = call(client, t, ok_call)
    assert (c["state"], c["end_reason"]) == ("completed", "transferred")
    assert [x["to_state"] for x in c["transitions"]][-2:] == ["transferring", "completed"]
    assert client.post(f"/internal/v1/calls/{ok_call}/transfer", headers=h, json={"target": 0}).status_code == 409

    bad = ring(client, t, n["e164"])["call_id"]
    h2 = worker(redis_client, bad)
    client.post(f"/internal/v1/calls/{bad}/bootstrap", headers=h2, json={"worker_id": "w1"})
    client.post(f"/internal/v1/calls/{bad}/state", headers=h2, json={"status": "active"})
    r = client.post(f"/internal/v1/calls/{bad}/transfer", headers=h2, json={"target": 1}).json()
    assert r["ok"] is False and "didn't answer" in r["reason"]
    assert call(client, t, bad)["state"] == "in_progress"  # back to the agent
    r = client.post(f"/internal/v1/calls/{bad}/transfer", headers=h2, json={"target": 2}).json()
    assert r == {"ok": False, "reason": "country_allowed"}
    assert client.post(f"/internal/v1/calls/{bad}/transfer", headers=h2, json={"target": 4}).status_code == 422
    n_dec = sql(
        owner_engine, "select count(*) from policy_decisions where purpose = 'transfer'", t["tenant_id"]
    ).scalar()
    assert n_dec == 3


def test_usage_is_billed_in_carrier_pulses(client, owner_engine):
    t, a, tr, n = setup_org(client, owner_engine)
    client.patch(f"/v1/telephony/trunks/{tr['id']}", headers=auth(t), json={"billing_pulse_seconds": 30})
    cid = ring(client, t, n["e164"])["call_id"]
    client.post(f"/v1/telephony/simulate/calls/{cid}/event", headers=auth(t), json={"status": "in_progress"})
    sql(
        owner_engine,
        "update calls set answered_at = now() - interval '61 seconds' where id = :i",
        t["tenant_id"],
        i=cid,
    )
    client.post(f"/v1/telephony/simulate/calls/{cid}/event", headers=auth(t), json={"status": "completed"})
    row = sql(
        owner_engine,
        "select pulse_seconds, billed_seconds, connected_seconds, direction, country_code "
        "from telephony_usage where call_id = :i",
        t["tenant_id"],
        i=cid,
    ).one()
    assert row[0] == 30 and row[1] == 90 and 61 <= float(row[2]) < 63 and row[3:] == ("inbound", "IN")


def test_recording_consent_on_the_call(client, owner_engine, redis_client):
    t, a, tr, n = setup_org(client, owner_engine, agent_cfg={"recording": {"policy": "ask_consent"}})
    cid = ring(client, t, n["e164"], caller="+919800000009")["call_id"]
    h = worker(redis_client, cid)
    boot = client.post(f"/internal/v1/calls/{cid}/bootstrap", headers=h, json={"worker_id": "w1"}).json()
    assert boot["config"]["telephony"]["recording"]["policy"] == "ask_consent"
    client.post(f"/internal/v1/calls/{cid}/consent", headers=h, json={"status": "declined", "said": "no thanks"})
    rec = client.get("/v1/consent", headers=auth(t), params={"phone": "+919800000009"}).json()
    assert [(r["purpose"], r["status"], r["source"], r["call_id"]) for r in rec] == [
        ("recording", "declined", "call", cid)
    ]


# ================================================================================================ adapters
def test_livekit_sip_adapter_requests(monkeypatch):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append((req.url.path.rsplit("/", 1)[1], body, req.headers["authorization"]))
        method = req.url.path.rsplit("/", 1)[1]
        if method == "CreateSIPParticipant" and body["sip_call_to"].endswith("2"):
            return httpx.Response(400, json={"code": "unavailable", "msg": "busy", "meta": {"sip_status_code": "486"}})
        return httpx.Response(
            200, json={"sip_trunk_id": "ST_1", "sip_dispatch_rule_id": "SDR_1", "sip_call_id": "SC_1"}
        )

    livekit_sip._transport = httpx.MockTransport(handler)
    lk = livekit_sip.LiveKitSip()
    spec = TrunkSpec(
        id="t1",
        name="Office",
        direction="both",
        address="sip.example.net",
        transport="tls",
        auth_username="u",
        auth_password="p",
        allowed_addresses=["203.0.113.5"],
        numbers=["+918041234567"],
    )
    ids = run(lk.sync_trunk(spec, {"inbound": "OLD_IN", "outbound": None, "dispatch": "OLD_RULE"}))
    assert ids == {"inbound": "ST_1", "outbound": "ST_1", "dispatch": "SDR_1"}
    methods = [m for m, _, _ in seen]
    assert methods == [
        "DeleteSIPDispatchRule",
        "DeleteSIPTrunk",
        "CreateSIPInboundTrunk",
        "CreateSIPDispatchRule",
        "CreateSIPOutboundTrunk",
    ]
    rule = seen[3][1]["rule"]["dispatch_rule_individual"]
    assert rule["room_prefix"] == "xvin_" and seen[4][1]["trunk"]["transport"] == "SIP_TRANSPORT_TLS"
    claims = jwt.decode(seen[2][2].split()[1], get_settings().livekit_api_secret, algorithms=["HS256"])
    assert claims["sip"] == {"admin": True, "call": True} and claims["exp"] - time.time() <= 61
    req = PlaceRequest(
        call_id="c1",
        room="xvout_1",
        participant_identity="phone-1",
        to_e164=OK,
        from_e164="+91804",
        outbound_trunk_id="ST_1",
        ring_timeout_seconds=30,
    )
    ok = run(lk.place_call(req))
    assert ok.outcome == "answered" and ("sip_call_id", "SC_1") in ok.refs
    assert seen[-1][1]["wait_until_answered"] is True and seen[-1][1]["ringing_timeout"] == "30s"
    busy = run(lk.place_call(PlaceRequest(**{**req.__dict__, "to_e164": BUSY})))
    assert (busy.outcome, busy.sip_status) == ("busy", 486)
    run(lk.transfer(room="xvin_1", participant_identity="sip_1", to_e164="+919812345678"))
    assert seen[-1][0] == "TransferSIPParticipant" and seen[-1][1]["transfer_to"] == "tel:+919812345678"
    assert [outcome_for_sip_status(c) for c in (200, 486, 603, 480, 487, 503, None)] == [
        "answered",
        "busy",
        "busy",
        "no_answer",
        "no_answer",
        "failed",
        "failed",
    ]


def test_simulated_carrier_is_refused_outside_development(client, owner_engine, monkeypatch):
    t = register(client)
    monkeypatch.setattr(type(get_settings()), "is_production_like", property(lambda self: True))
    r = client.post("/v1/telephony/trunks", headers=auth(t), json={"name": "x", "provider_key": "simulated"})
    assert r.status_code == 422
    assert carrier_post(client, b"{}").status_code == 404
    assert "simulated" not in [p["key"] for p in client.get("/v1/telephony/providers", headers=auth(t)).json()]


def test_new_tables_force_rls_and_histories_are_append_only(owner_engine):
    tables = (
        "sip_trunks",
        "phone_numbers",
        "call_queues",
        "inbound_routes",
        "destination_policies",
        "call_provider_refs",
        "call_provider_events",
        "call_state_transitions",
        "telephony_usage",
        "consent_records",
        "suppression_entries",
        "campaigns",
        "campaign_contacts",
        "dial_attempts",
        "policy_decisions",
    )
    with owner_engine.connect() as c:
        rows = dict(
            c.execute(
                text("select relname, relforcerowsecurity from pg_class where relname = any(:t)"), {"t": list(tables)}
            ).all()
        )
        assert rows == dict.fromkeys(tables, True)
        for table in (
            "policy_decisions",
            "call_state_transitions",
            "telephony_usage",
            "consent_records",
            "suppression_entries",
        ):
            assert (
                c.execute(text("select has_table_privilege('xplovoice_app', :t, 'DELETE')"), {"t": table}).scalar()
                is False
            ), table
        for table in ("policy_decisions", "call_state_transitions", "telephony_usage"):
            assert (
                c.execute(text("select has_table_privilege('xplovoice_app', :t, 'UPDATE')"), {"t": table}).scalar()
                is False
            ), table
