# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 8: Healthcare Mode (M19-M25). Every person, number and conversation here is synthetic: the numbers are
from the 555 fictional range and the names are made up. Nothing here is real PHI."""

import json
import os
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from xplovoice_api.core.config import get_settings
from xplovoice_api.core.db import session_scope
from xplovoice_api.modules.m03_ai.routing import candidates
from xplovoice_api.modules.m05_agents.runtime import HEALTHCARE_GUARDRAIL, engine_config
from xplovoice_api.modules.m05_agents.schemas import AgentConfig
from xplovoice_api.modules.m19_healthcare.mode import phi_mode, recording_policy
from xplovoice_api.modules.m20_phi.classify import mask_number, minimize, redact
from xplovoice_api.modules.m23_audit.router import notification_plan

from .conftest import auth, register
from .test_ai import mock_routes
from .test_telephony import number, publish, ring, sql, trunk
from .test_tenancy import _mfa_login, invite_and_join
from .test_voice import make_agent

REASON = "Synthetic healthcare test"
CLINIC_LINE = "+14155550100"
PATIENT = "+14155550123"  # fictional 555 number
SAID = "My date of birth is 04/12/1961 and my member id is MRN 88812345"


@pytest.fixture(autouse=True)
def _healthcare_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "healthcare_enabled", True)


@pytest.fixture
def admin(client, owner_engine):
    staff = register(client, org="Xplosys Ops")
    with owner_engine.begin() as c:
        c.execute(text("update users set is_platform_admin = true where email = :e"), {"e": staff["email"]})
    return _mfa_login(client, staff)


# ------------------------------------------------------------------ helpers
def mfa(client, t):
    """Turns on two-factor and signs in again with it (the account's email is kept for later sign-ins)."""
    out = _mfa_login(client, t)
    out["email"] = t["email"]
    return out


def member(client, owner, role):
    email = f"{role}-{owner['tenant_id'][:6]}@example.com"
    t = invite_and_join(client, owner, role, email=email)
    t["email"] = email
    return t


def approve_mock_for_phi(client, admin, *, expires_on=None):
    r = client.post(
        "/admin/v1/healthcare/vendors",
        headers=auth(admin),
        json={
            "vendor_type": "ai_provider",
            "vendor_key": "mock",
            "vendor_name": "Mock AI (synthetic)",
            "baa_status": "signed",
            "signed_on": "2026-01-01",
            "expires_on": expires_on,
            "reference": "Synthetic BAA, test only",
            "reason": REASON,
        },
    )
    assert r.status_code == 201, r.text
    providers = {p["key"]: p for p in client.get("/admin/v1/ai/providers", headers=auth(admin)).json()}
    r = client.patch(
        f"/admin/v1/ai/providers/{providers['mock']['id']}",
        headers=auth(admin),
        json={"phi_eligible": True, "reason": REASON},
    )
    assert r.status_code == 200, r.text


def request(client, t, **kw):
    body = {
        "entity_type": "covered_entity",
        "privacy_contact": "Privacy Office, Sunrise Clinic",
        "synthetic_data_only": True,
    }
    return client.post("/v1/healthcare/request", headers=auth(t), json=body | kw)


def gate(client, t):
    return {c["key"]: c["ok"] for c in client.get("/v1/healthcare", headers=auth(t)).json()["gate"]}


def approved_policy(client, author, approver, **kw):
    body = {"recording_mode": "consent_required", "privacy_notice": "", "change_note": "First policy"} | kw
    r = client.post("/v1/healthcare/policies", headers=auth(author), json=body)
    assert r.status_code == 201, r.text
    r = client.post(f"/v1/healthcare/policies/{r.json()['id']}/approve", headers=auth(approver))
    assert r.status_code == 200, r.text
    return r.json()


def ready_org(client, owner_engine, admin, *, activate=True, entity="covered_entity"):
    """A US clinic with everything the gate needs; activated unless told otherwise."""
    t = mfa(client, register(client, country="US", org="Sunrise Clinic (synthetic)"))
    mock_routes(client, t, owner_engine)
    approve_mock_for_phi(client, admin)
    assert request(client, t, entity_type=entity).status_code == 201
    po = mfa(client, member(client, t, "privacy_officer"))
    approved_policy(client, t, po)
    assert (
        client.put("/v1/retention/policies/call_content", headers=auth(t), json={"retain_days": 30}).status_code == 200
    )
    r = client.post(
        f"/admin/v1/healthcare/tenants/{t['tenant_id']}/baa",
        headers=auth(admin),
        json={
            "title": "BAA with Sunrise Clinic",
            "signed_on": "2026-11-01",
            "reference": "Synthetic, test only",
            "reason": REASON,
        },
    )
    assert r.status_code == 201, r.text
    r = client.post("/admin/v1/healthcare/control-tests/run", headers=auth(admin), json={"reason": REASON})
    assert r.status_code == 201 and r.json()["details"]["passed"], r.text
    if activate:
        r = client.post(
            f"/admin/v1/healthcare/tenants/{t['tenant_id']}/activate", headers=auth(admin), json={"reason": REASON}
        )
        assert r.status_code == 200, r.text
    return t, po


def phone_call(client, owner_engine, t, said=SAID):
    a = make_agent(client, t)
    publish(owner_engine, a["id"], t["tenant_id"])
    tr = trunk(client, t)
    n = number(client, t, tr, CLINIC_LINE)
    assert (
        client.put(f"/v1/phone-numbers/{n['id']}/route", headers=auth(t), json={"agent_id": a["id"]}).status_code == 200
    )
    call_id = ring(client, t, CLINIC_LINE, caller=PATIENT)["call_id"]
    sql(
        owner_engine,
        "insert into transcript_segments (tenant_id, call_id, seq, speaker, text) values (:t, :c, 0, 'caller', :x)",
        t["tenant_id"],
        t=t["tenant_id"],
        c=call_id,
        x=said,
    )
    sql(
        owner_engine,
        "insert into call_events (tenant_id, call_id, event_key, type, data) values (:t, :c, 'x1', 'tool.ran', "
        "cast(:d as jsonb))",
        t["tenant_id"],
        t=t["tenant_id"],
        c=call_id,
        d=json.dumps({"said": said}),
    )
    return call_id


def end_call(owner_engine, t, call_id, days_ago):
    sql(
        owner_engine,
        "update calls set ended_at = now() - make_interval(days => :d), status = 'completed' where id = :c",
        t["tenant_id"],
        c=call_id,
        d=days_ago,
    )


def phi_log(owner_engine, t):
    return (
        sql(
            owner_engine,
            "select * from phi_access_audit_logs where tenant_id = :t order by id",
            t["tenant_id"],
            t=t["tenant_id"],
        )
        .mappings()
        .all()
    )


# ------------------------------------------------------------------ M20 (pure)
def test_redaction_masks_identifiers_and_minimize_keeps_only_ids():
    out, found = redact("Call +1 415 555 0123 or jo@example.com, SSN 123-45-6789, DOB 04/12/1961, MRN 88812345")
    assert "555" not in out and "jo@" not in out and "6789" not in out and "1961" not in out and "88812345" not in out
    assert {"PHONE", "EMAIL", "SSN", "DATE", "MRN"} <= set(found)
    assert redact("The booking moved to Tuesday")[0] == "The booking moved to Tuesday"
    m = minimize({"id": "t1", "subject": "Refill for Jo", "status": "open", "requester": {"phone": PATIENT}})
    assert m == {"id": "t1", "subject": "[withheld]", "status": "open", "requester": {"phone": "[withheld]"}}
    assert mask_number(PATIENT) == "+1••••••0123"


# ------------------------------------------------------------------ M19
def test_healthcare_mode_is_off_by_default_and_changes_nothing(client, owner_engine):
    t = register(client, country="US")
    body = client.get("/v1/healthcare", headers=auth(t)).json()
    assert body["mode"] == "off" and body["phi_protections"] is False and body["gate_passed"] is False
    with session_scope(tenant_id=t["tenant_id"]) as s:
        assert phi_mode(s) is False
        assert recording_policy(s, "record") == "record"
    viewer = member(client, t, "viewer")
    assert client.get("/v1/healthcare", headers=auth(viewer)).status_code == 403  # healthcare:read


def test_request_needs_us_two_factor_and_synthetic_data(client, owner_engine):
    india = mfa(client, register(client, country="IN"))
    assert request(client, india).json()["detail"]["code"] == "jurisdiction"
    t = register(client, country="US")
    assert request(client, t).status_code == 403  # no two-factor session
    t = mfa(client, t)
    assert request(client, t, synthetic_data_only=False).json()["detail"]["code"] == "synthetic_data_only"
    r = request(client, t)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["mode"] == "requested" and body["phi_protections"] is False
    cls = {c["resource_type"]: c for c in body["classifications"]}
    assert cls["call_transcript"]["classification"] == "phi" and cls["call_transcript"]["locked"]
    r = client.put(
        "/v1/healthcare/classifications/call_transcript", headers=auth(t), json={"classification": "not_phi"}
    )
    assert r.status_code == 409
    r = client.put("/v1/healthcare/classifications/knowledge_document", headers=auth(t), json={"classification": "phi"})
    assert r.status_code == 200
    assert request(client, t).status_code == 409
    assert client.post("/v1/healthcare/withdraw", headers=auth(t)).json()["mode"] == "withdrawn"
    assert request(client, t).status_code == 201  # may ask again


def test_policy_versions_need_a_second_person(client, owner_engine):
    t = mfa(client, register(client, country="US"))
    request(client, t)
    po = member(client, t, "privacy_officer")
    r = client.post("/v1/healthcare/policies", headers=auth(t), json={"recording_mode": "off", "change_note": "First"})
    v1 = r.json()
    assert v1["version"] == 1 and v1["status"] == "draft"
    assert client.post(f"/v1/healthcare/policies/{v1['id']}/approve", headers=auth(t)).status_code == 403
    assert client.post(f"/v1/healthcare/policies/{v1['id']}/approve", headers=auth(po)).json()["status"] == "approved"
    v2 = approved_policy(client, po, t, recording_mode="consent_required", change_note="Allow recording with consent")
    body = client.get("/v1/healthcare", headers=auth(t)).json()
    assert body["policy_version_in_force"] == v2["version"] == 2
    assert {p["version"]: p["status"] for p in body["policies"]} == {2: "approved", 1: "superseded"}
    operator = member(client, t, "operator")
    assert (
        client.post("/v1/healthcare/policies", headers=auth(operator), json={"change_note": "x" * 5}).status_code == 403
    )


def test_activation_gate_and_four_eyes(client, owner_engine, admin):
    t, _ = ready_org(client, owner_engine, admin, activate=False)
    assert all(gate(client, t).values())
    # The requester can't activate their own organisation, even as a platform admin.
    with owner_engine.begin() as c:
        c.execute(text("update users set is_platform_admin = true where email = :e"), {"e": t["email"]})
    r = client.post(f"/admin/v1/healthcare/tenants/{t['tenant_id']}/activate", headers=auth(t), json={"reason": REASON})
    assert r.status_code == 403
    # A member without two-factor fails the gate, and activation is refused (and audited).
    viewer = member(client, t, "viewer")
    assert gate(client, t)["mfa"] is False
    r = client.post(
        f"/admin/v1/healthcare/tenants/{t['tenant_id']}/activate", headers=auth(admin), json={"reason": REASON}
    )
    assert r.status_code == 409 and "mfa" in r.json()["detail"]["message"]
    mfa(client, viewer)
    r = client.post(
        f"/admin/v1/healthcare/tenants/{t['tenant_id']}/activate", headers=auth(admin), json={"reason": REASON}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active" and r.json()["gate_passed"]
    snap = sql(
        owner_engine, "select gate_snapshot, activated_by_user_id from healthcare_tenant_profiles", t["tenant_id"]
    ).one()
    assert {c["key"] for c in snap.gate_snapshot["checks"]} >= {"customer_baa", "phi_providers", "control_tests"}
    actions = {r.action for r in sql(owner_engine, "select action from audit_log where tenant_id is null").all()}
    assert {"admin.healthcare_activation_refused", "admin.healthcare_activated", "admin.control_tests_run"} <= actions
    # Without the platform switch nothing can be activated.
    get_settings().healthcare_enabled = False
    assert gate(client, t)["platform_enabled"] is False


def test_gate_names_what_is_missing(client, owner_engine, admin):
    t = mfa(client, register(client, country="US"))
    mock_routes(client, t, owner_engine)
    request(client, t)
    g = gate(client, t)
    assert g["requested"] and g["jurisdiction"] and g["synthetic_data"]
    for key in ("customer_baa", "policy", "retention", "privacy_officer", "phi_providers", "control_tests"):
        assert g[key] is False, key
    # A BAA that has expired does not count.
    approve_mock_for_phi(client, admin, expires_on="2026-02-01")
    assert gate(client, t)["phi_providers"] is False


# ------------------------------------------------------------------ M21 (HC-002, HC-010)
def test_phi_goes_only_to_providers_with_a_baa_in_force_including_fallback(client, owner_engine, admin):
    t, _ = ready_org(client, owner_engine, admin)
    a = make_agent(client, t)
    chat = client.post(f"/v1/agents/{a['id']}/chat", headers=auth(t), json={}).json()["call_id"]
    assert (
        client.post(f"/v1/calls/{chat}/chat", headers=auth(t), json={"text": "When are you open?"}).status_code == 200
    )
    # Terminating the vendor's BAA withdraws its PHI approval at once: no provider remains, so nothing is sent.
    r = client.post(
        "/admin/v1/healthcare/vendors",
        headers=auth(admin),
        json={
            "vendor_type": "ai_provider",
            "vendor_key": "mock",
            "vendor_name": "Mock AI (synthetic)",
            "baa_status": "terminated",
            "reference": "Synthetic termination",
            "reason": REASON,
        },
    )
    assert r.status_code == 201
    r = client.post(f"/v1/calls/{chat}/chat", headers=auth(t), json={"text": "Can I book?"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "no_provider_available"
    with session_scope(tenant_id=t["tenant_id"]) as s:
        cands, skipped = candidates(s, kind="llm")
        assert cands == [] and "health information" in skipped[0].reason
    elig = {v["vendor_key"]: v for v in client.get("/v1/vendors/eligibility", headers=auth(t)).json()}
    assert elig["mock"]["eligible"] is False
    # An organisation without healthcare mode is unaffected.
    other = register(client, country="US")
    mock_routes(client, other, owner_engine)
    with session_scope(tenant_id=other["tenant_id"]) as s:
        assert candidates(s, kind="llm")[0]


def test_expired_vendor_baa_is_skipped(client, owner_engine, admin):
    t, _ = ready_org(client, owner_engine, admin)
    approve_mock_for_phi(client, admin, expires_on=(date.today() - timedelta(days=1)).isoformat())
    with session_scope(tenant_id=t["tenant_id"]) as s:
        cands, skipped = candidates(s, kind="tts")
    assert cands == [] and "expired" in skipped[0].reason


# ------------------------------------------------------------------ PHI access (HC-004, HC-006)
def test_phi_is_withheld_without_phi_read_and_every_access_is_logged(client, owner_engine, admin):
    t, po = ready_org(client, owner_engine, admin)
    call_id = phone_call(client, owner_engine, t)
    viewer, operator = member(client, t, "viewer"), member(client, t, "operator")

    v = client.get(f"/v1/calls/{call_id}", headers=auth(viewer)).json()
    assert v["phi_restricted"] and v["transcript"] == [] and v["events"] == []
    assert v["from_number"] == mask_number(PATIENT)
    listed = client.get("/v1/calls", headers=auth(viewer)).json()
    assert listed[0]["from_number"] == mask_number(PATIENT) and listed[0]["phi_restricted"]

    o = client.get(f"/v1/calls/{call_id}", headers=auth(operator)).json()
    assert not o["phi_restricted"] and o["transcript"][0]["text"] == SAID and o["from_number"] == PATIENT

    rows = phi_log(owner_engine, t)
    assert [(r["action"], r["result"]) for r in rows if r["resource_type"] == "call_transcript"] == [
        ("view", "denied"),
        ("view", "allowed"),
    ]
    assert all(r["correlation_id"] for r in rows)
    assert client.get("/v1/audit/phi-access", headers=auth(viewer)).status_code == 403
    assert client.get("/v1/audit/phi-access", headers=auth(operator)).status_code == 403
    log = client.get("/v1/audit/phi-access", headers=auth(po), params={"resource_id": call_id}).json()
    assert {r["result"] for r in log} == {"allowed", "denied"}
    # Another organisation sees none of it.
    other = register(client, country="US")
    assert client.get(f"/v1/calls/{call_id}", headers=auth(other)).status_code == 404


# ------------------------------------------------------------------ HC-007: no PHI in logs or webhooks
def test_audit_log_phi_log_and_webhooks_hold_no_phi(client, owner_engine, admin):
    t, po = ready_org(client, owner_engine, admin)
    call_id = phone_call(client, owner_engine, t)
    client.get(f"/v1/calls/{call_id}", headers=auth(t))
    client.post(f"/v1/recordings/{call_id}/access-check", headers=auth(t), json={"purpose": "quality_review"})
    r = client.post(
        "/v1/tickets",
        headers=auth(t),
        json={"subject": "Refill question from Jo Rivera", "requester_name": "Jo Rivera", "requester_phone": PATIENT},
    )
    assert r.status_code == 201, r.text
    ev = sql(owner_engine, "select payload from integration_events where type = 'ticket.created'", t["tenant_id"]).one()
    assert ev.payload["subject"] == "[withheld]" and ev.payload["id"] == r.json()["id"]
    dump = json.dumps(
        [
            dict(x)
            for x in sql(
                owner_engine,
                "select action, reason, metadata, resource_id from audit_log where tenant_id = :t",
                t["tenant_id"],
                t=t["tenant_id"],
            ).mappings()
        ]
        + [dict(x) for x in phi_log(owner_engine, t)],
        default=str,
    )
    for secret in (PATIENT, PATIENT[2:], "1961", "88812345", "Jo Rivera"):
        assert secret not in dump, secret


# ------------------------------------------------------------------ M22: recording (HC-008)
def test_recording_needs_consent_a_phi_role_and_the_policy(client, owner_engine, admin):
    t, po = ready_org(client, owner_engine, admin)
    call_id = phone_call(client, owner_engine, t)
    viewer = member(client, t, "viewer")
    chk = lambda tok: client.post(f"/v1/recordings/{call_id}/access-check", headers=auth(tok), json={}).json()  # noqa: E731
    assert chk(viewer)["allowed"] is False
    no_consent = chk(t)
    assert no_consent["allowed"] is False and "consent" in no_consent["reason"]
    sql(
        owner_engine,
        "insert into consent_records (tenant_id, phone, purpose, status, basis, source, call_id) "
        "values (:t, :p, 'recording', 'granted', 'on_call', 'call', :c)",
        t["tenant_id"],
        t=t["tenant_id"],
        p=PATIENT,
        c=call_id,
    )
    ok = chk(t)
    assert ok["allowed"] and ok["consent_recorded"] and ok["recording_available"] is False
    assert [r["result"] for r in phi_log(owner_engine, t) if r["action"] == "access_check"] == [
        "denied",
        "denied",
        "allowed",
    ]
    with session_scope(tenant_id=t["tenant_id"]) as s:
        assert recording_policy(s, "record") == "ask_consent"  # policy: consent_required
        assert recording_policy(s, "off") == "off"
    approved_policy(client, po, t, recording_mode="off", change_note="No recording")
    with session_scope(tenant_id=t["tenant_id"]) as s:
        assert recording_policy(s, "ask_consent") == "off"


def test_every_agent_gets_the_guardrail_and_the_privacy_notice(client, owner_engine, admin):
    cfg = AgentConfig(agent_type="receptionist", greeting="Hello, Sunrise Clinic.")
    plain = engine_config(cfg, "Asha", open_now=True, max_seconds_cap=600)
    assert HEALTHCARE_GUARDRAIL not in plain["instructions"]
    hc = engine_config(
        cfg, "Asha", open_now=True, max_seconds_cap=600, healthcare=True, privacy_notice="This line is private."
    )
    assert HEALTHCARE_GUARDRAIL in hc["instructions"]
    assert hc["greeting"] == "This line is private. Hello, Sunrise Clinic."


# ------------------------------------------------------------------ M24: retention (HC-009)
def test_retention_purges_old_call_content_except_under_legal_hold(client, owner_engine, admin):
    t, po = ready_org(client, owner_engine, admin)
    old = phone_call(client, owner_engine, t)
    held = client.post(
        "/v1/telephony/simulate/inbound", headers=auth(t), json={"to": CLINIC_LINE, "caller": "+14155550199"}
    )
    held_id = held.json()["call_id"]
    recent = client.post(
        "/v1/telephony/simulate/inbound", headers=auth(t), json={"to": CLINIC_LINE, "caller": "+14155550188"}
    )
    end_call(owner_engine, t, old, 40)
    end_call(owner_engine, t, held_id, 40)
    end_call(owner_engine, t, recent.json()["call_id"], 5)
    r = client.post(
        "/v1/retention/holds",
        headers=auth(po),
        json={"scope": "call", "call_id": held_id, "reason": "Synthetic dispute"},
    )
    assert r.status_code == 201, r.text
    hold = r.json()
    run = client.post("/v1/retention/run", headers=auth(po)).json()
    assert (run["calls_purged"], run["skipped_on_hold"]) == (1, 1)
    c = client.get(f"/v1/calls/{old}", headers=auth(po)).json()
    assert c["content_purged"] and c["transcript"] == [] and c["from_number"] is None
    assert all(e["data"] == {"purged": True} for e in c["events"])
    # The application role can't remove content any other way.
    app = create_engine(os.environ["XV_DATABASE_URL"])
    with pytest.raises(ProgrammingError), app.begin() as conn:
        conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": t["tenant_id"]})
        conn.execute(text("delete from transcript_segments"))
    # The database function itself refuses a held call.
    with pytest.raises(DBAPIError, match="legal_hold"), app.begin() as conn:
        conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": t["tenant_id"]})
        conn.execute(text("select purge_call_content(:c)"), {"c": held_id})
    app.dispose()
    client.post(f"/v1/retention/holds/{hold['id']}/release", headers=auth(po), json={"reason": "Dispute settled"})
    assert client.post("/v1/retention/run", headers=auth(po)).json()["calls_purged"] == 1
    assert [r["action"] for r in phi_log(owner_engine, t)].count("purge") == 2
    viewer = member(client, t, "viewer")
    assert client.post("/v1/retention/run", headers=auth(viewer)).status_code == 403


def test_rights_requests_are_decided_by_a_second_person_exported_and_deleted(client, owner_engine, admin):
    t, po = ready_org(client, owner_engine, admin)
    call_id = phone_call(client, owner_engine, t)
    r = client.post(
        "/v1/retention/requests",
        headers=auth(po),
        json={"kind": "access", "subject_phone": PATIENT, "subject_reference": "R-1"},
    )
    req = r.json()
    assert req["status"] == "received" and req["due_at"] > req["received_at"]
    assert (
        client.post(
            f"/v1/retention/requests/{req['id']}/decide",
            headers=auth(po),
            json={"decision": "approve", "reason": "Identity checked"},
        ).status_code
        == 403
    )
    r = client.post(
        f"/v1/retention/requests/{req['id']}/decide",
        headers=auth(t),
        json={"decision": "approve", "reason": "Identity checked"},
    )
    assert r.json()["status"] == "approved"
    export = client.get(f"/v1/retention/requests/{req['id']}/export", headers=auth(po)).json()
    assert export["calls"][0]["call_id"] == call_id and export["calls"][0]["transcript"][0]["text"] == SAID
    assert "export" in [x["action"] for x in phi_log(owner_engine, t)]

    d = client.post(
        "/v1/retention/requests", headers=auth(po), json={"kind": "deletion", "subject_phone": PATIENT}
    ).json()
    client.post(
        f"/v1/retention/requests/{d['id']}/decide",
        headers=auth(t),
        json={"decision": "approve", "reason": "Policy allows"},
    )
    hold = client.post(
        "/v1/retention/holds", headers=auth(po), json={"scope": "phone", "phone": PATIENT, "reason": "Synthetic audit"}
    ).json()
    r = client.post(f"/v1/retention/requests/{d['id']}/complete", headers=auth(po), json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "legal_hold"
    assert client.get(f"/v1/calls/{call_id}", headers=auth(po)).json()["transcript"]  # untouched, all or nothing
    client.post(f"/v1/retention/holds/{hold['id']}/release", headers=auth(po), json={"reason": "Audit finished"})
    r = client.post(f"/v1/retention/requests/{d['id']}/complete", headers=auth(po), json={"note": "Done"})
    assert r.json()["status"] == "completed" and r.json()["outcome"]["purged"] == 1
    assert client.get(f"/v1/calls/{call_id}", headers=auth(po)).json()["transcript"] == []
    # Another organisation can't reach the request.
    other = register(client, country="US")
    assert client.get(f"/v1/retention/requests/{d['id']}/export", headers=auth(other)).status_code in (403, 404)


# ------------------------------------------------------------------ M23: incidents and breach
def test_incident_assessment_schedules_the_right_notices(client, owner_engine, admin):
    t, po = ready_org(client, owner_engine, admin)
    viewer = member(client, t, "viewer")
    found = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    r = client.post(
        "/v1/incidents",
        headers=auth(viewer),
        json={
            "title": "Fax sent to the wrong number",
            "summary": "Patient 123-45-6789 on +1 415 555 0123 details were faxed wrongly",
            "category": "misdirected_communication",
            "severity": "medium",
            "affected_individuals": 3,
            "discovered_at": found,
        },
    )
    assert r.status_code == 201, r.text
    inc = r.json()
    assert "6789" not in inc["summary"] and "[SSN]" in inc["summary"]
    assert client.get("/v1/incidents", headers=auth(viewer)).status_code == 403
    factors = {
        "nature_and_extent": "Names and appointment times",
        "unauthorized_recipient": "Another clinic bound by HIPAA",
        "acquired_or_viewed": "Returned unread",
        "mitigation": "Recipient confirmed destruction",
    }
    low = client.post(f"/v1/incidents/{inc['id']}/assessment", headers=auth(po), json=factors | {"risk": "low"}).json()
    assert low["determination"] == "not_a_breach" and low["notifications"] == []
    high = client.post(
        f"/v1/incidents/{inc['id']}/assessment", headers=auth(po), json=factors | {"risk": "not_low"}
    ).json()
    assert high["determination"] == "breach" and high["status"] == "notifying"
    plan = {n["audience"]: n for n in high["notifications"]}
    assert set(plan) == {"individuals", "hhs"}  # fewer than 500: no media notice, HHS after the year ends
    assert plan["hhs"]["due_at"] > plan["individuals"]["due_at"]
    assert (
        client.post(f"/v1/incidents/{inc['id']}/close", headers=auth(po), json={"note": "Handled fully"}).status_code
        == 409
    )
    for n in high["notifications"]:
        client.post(
            f"/v1/incidents/{inc['id']}/notifications/{n['id']}/sent", headers=auth(po), json={"method": "Letter"}
        )
    closed = client.post(f"/v1/incidents/{inc['id']}/close", headers=auth(po), json={"note": "Handled fully"}).json()
    assert closed["status"] == "closed"
    assert client.get("/admin/v1/healthcare/incidents", headers=auth(admin)).json()[0]["id"] == inc["id"]
    other = register(client, country="US")
    assert client.get(f"/v1/incidents/{inc['id']}", headers=auth(other)).status_code in (403, 404)


def test_notification_plan_for_large_breaches_and_business_associates():
    class Inc:
        discovered_at = datetime(2026, 11, 1, tzinfo=UTC)
        affected_individuals = 600

    big = dict(notification_plan(Inc(), False))
    assert set(big) == {"individuals", "hhs", "media"} and big["hhs"] == Inc.discovered_at + timedelta(days=60)
    assert [a for a, _ in notification_plan(Inc(), True)] == ["covered_entity"]


# ------------------------------------------------------------------ M25: evidence, controls, report
def test_control_tests_evidence_and_report(client, owner_engine, admin):
    t, po = ready_org(client, owner_engine, admin)
    runs = client.get("/admin/v1/healthcare/control-tests", headers=auth(admin)).json()
    results = {r["key"]: r["passed"] for r in runs[0]["details"]["results"]}
    assert results == dict.fromkeys(
        ("rls_forced", "runtime_role", "append_only", "purge_guarded", "phi_vendors", "secrets"), True
    )
    r = client.post("/v1/compliance/evidence", headers=auth(po), json={"kind": "customer_baa", "title": "Fake BAA"})
    assert r.status_code == 422  # only Xplosys records customer BAAs
    r = client.post(
        "/v1/compliance/evidence", headers=auth(po), json={"kind": "risk_assessment", "title": "2026 risk analysis"}
    )
    assert r.status_code == 201
    app = create_engine(os.environ["XV_DATABASE_URL"])
    with pytest.raises(ProgrammingError), app.begin() as conn:  # RLS refuses it at the database too
        conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": t["tenant_id"]})
        conn.execute(
            text(
                "insert into compliance_evidence (tenant_id, kind, title, recorded_kind) "
                "values (:t, 'customer_baa', 'Forged', 'platform')"
            ),
            {"t": t["tenant_id"]},
        )
    app.dispose()
    risk = client.post(
        "/v1/compliance/risks", headers=auth(po), json={"title": "Staff reuse passwords", "likelihood": 3, "impact": 4}
    ).json()
    assert risk["score"] == 12
    rep = client.get("/v1/compliance/report", headers=auth(po)).json()
    assert rep["mode"] == "active" and all(c["ok"] for c in rep["gate"])
    assert {e["kind"] for e in rep["evidence"]} >= {"customer_baa", "control_test", "risk_assessment"}
    assert rep["open_risks"][0]["title"] == "Staff reuse passwords" and rep["retention"] == {"call_content": 30}
    assert "not a certification" in rep["statement"]


def test_a_failing_control_test_blocks_activation(client, owner_engine, admin):
    t, _ = ready_org(client, owner_engine, admin, activate=False)
    # A provider approved for PHI without a BAA in force fails the vendor control.
    sql(owner_engine, "update ai_providers set baa_status = 'signed', phi_eligible = true where key = 'openai'")
    r = client.post("/admin/v1/healthcare/control-tests/run", headers=auth(admin), json={"reason": REASON}).json()
    assert r["details"]["passed"] is False
    assert gate(client, t)["control_tests"] is False


# ------------------------------------------------------------------ suspension
def test_suspension_stops_new_calls_but_keeps_every_protection(client, owner_engine, admin):
    t, po = ready_org(client, owner_engine, admin)
    call_id = phone_call(client, owner_engine, t)
    a = make_agent(client, t)
    r = client.post(
        f"/admin/v1/healthcare/tenants/{t['tenant_id']}/suspend", headers=auth(admin), json={"reason": REASON}
    )
    assert r.json()["status"] == "suspended"
    r = client.post(f"/v1/agents/{a['id']}/chat", headers=auth(t), json={})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "healthcare_suspended"
    viewer = member(client, t, "viewer")
    assert client.get(f"/v1/calls/{call_id}", headers=auth(viewer)).json()["phi_restricted"]
    mfa(client, viewer)  # the gate is checked again on resume
    r = client.post(
        f"/admin/v1/healthcare/tenants/{t['tenant_id']}/activate", headers=auth(admin), json={"reason": REASON}
    )
    assert r.json()["status"] == "active"
    assert client.post(f"/v1/agents/{a['id']}/chat", headers=auth(t), json={}).status_code == 201


def test_privacy_officer_role(client, owner_engine):
    t = mfa(client, register(client, country="US"))
    po = member(client, t, "privacy_officer")
    assert client.get("/v1/healthcare", headers=auth(po)).status_code == 200
    assert client.post("/v1/agents", headers=auth(po), json={"name": "x", "config": {}}).status_code == 403
    assert (
        client.post("/v1/invitations", headers=auth(po), json={"email": "a@example.com", "role": "viewer"}).status_code
        == 403
    )
    team = client.get("/v1/members", headers=auth(t))
    assert "privacy_officer" in {m["role"] for m in team.json()}
