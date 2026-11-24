# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""M02 tenant management, RBAC and member lifecycle."""

import pyotp
from sqlalchemy import text

from .conftest import PASSWORD, auth, register


def invite_and_join(client, owner, role, email=None):
    email = email or f"{role}-{owner['tenant_id'][:6]}@example.com"
    inv = client.post("/v1/invitations", headers=auth(owner), json={"email": email, "role": role})
    assert inv.status_code == 201, inv.text
    token = inv.json()["accept_url"].split("token=")[1]
    r = client.post("/v1/invitations/accept-new", json={"token": token, "display_name": role, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()


def test_regional_settings_validation(client):
    t = register(client, country="US")
    h = auth(t)
    assert client.patch("/v1/tenants/current", headers=h, json={"timezone": "Mars/Base"}).status_code == 422
    assert client.patch("/v1/tenants/current", headers=h, json={"default_language": "hi-IN"}).status_code == 422
    r = client.patch(
        "/v1/tenants/current",
        headers=h,
        json={"business_phone": "+1 (415) 555-2671", "timezone": "America/Los_Angeles"},
    )
    assert r.status_code == 200
    assert r.json()["business_phone"] == "+14155552671"  # stored as E.164
    assert client.patch("/v1/tenants/current", headers=h, json={"business_phone": "12345"}).status_code == 422


def test_reference_countries(client):
    data = {c["code"]: c for c in client.get("/v1/reference/countries").json()}
    assert {lang["name"] for lang in data["IN"]["languages"]} == {"Hindi", "Hinglish", "Indian English"}
    assert data["US"]["currency"] == "USD"


def test_invitation_flow_and_roles(client):
    owner = register(client)
    viewer = invite_and_join(client, owner, "viewer")
    me = client.get("/v1/auth/me", headers=auth(viewer)).json()
    assert me["role"] == "viewer" and me["tenant_id"] == owner["tenant_id"]
    members = client.get("/v1/members", headers=auth(owner)).json()
    assert {m["role"] for m in members} == {"owner", "viewer"}


def test_viewer_cannot_manage_and_denial_is_audited(client, owner_engine):
    owner = register(client)
    viewer = invite_and_join(client, owner, "viewer")
    r = client.post("/v1/invitations", headers=auth(viewer), json={"email": "x@example.com", "role": "viewer"})
    assert r.status_code == 403
    assert client.patch("/v1/tenants/current", headers=auth(viewer), json={"name": "Hacked"}).status_code == 403
    with owner_engine.connect() as c:
        c.execute(text("select set_config('app.platform_admin', 'on', false)"))
        n = c.execute(text("select count(*) from audit_log where action = 'authz.denied'")).scalar()
    assert n == 2


def test_role_rank_and_last_owner_guards(client):
    owner = register(client)
    admin = invite_and_join(client, owner, "admin")
    members = {m["role"]: m for m in client.get("/v1/members", headers=auth(owner)).json()}
    # An admin cannot promote anyone to owner, nor touch the owner.
    r = client.patch(f"/v1/members/{members['admin']['id']}", headers=auth(admin), json={"role": "owner"})
    assert r.status_code == 403
    assert client.delete(f"/v1/members/{members['owner']['id']}", headers=auth(admin)).status_code == 403
    # The only owner cannot demote themselves.
    r = client.patch(f"/v1/members/{members['owner']['id']}", headers=auth(owner), json={"role": "admin"})
    assert r.status_code == 409


def test_role_change_ends_member_sessions(client):
    owner = register(client)
    admin = invite_and_join(client, owner, "admin")
    mid = next(m["id"] for m in client.get("/v1/members", headers=auth(owner)).json() if m["role"] == "admin")
    assert client.patch(f"/v1/members/{mid}", headers=auth(owner), json={"role": "viewer"}).status_code == 200
    assert client.get("/v1/auth/me", headers=auth(admin)).status_code == 401


def test_invitation_email_must_match_existing_account(client):
    owner = register(client)
    other = register(client, org="Other Org")
    inv = client.post("/v1/invitations", headers=auth(owner), json={"email": "someone@example.com", "role": "viewer"})
    token = inv.json()["accept_url"].split("token=")[1]
    assert client.post("/v1/invitations/accept", headers=auth(other), json={"token": token}).status_code == 403


def test_existing_user_joins_second_org_and_switches(client):
    a = register(client, org="Org A")
    b = register(client, org="Org B")
    inv = client.post("/v1/invitations", headers=auth(b), json={"email": a["email"], "role": "operator"})
    token = inv.json()["accept_url"].split("token=")[1]
    joined = client.post("/v1/invitations/accept", headers=auth(a), json={"token": token})
    assert joined.status_code == 200 and joined.json()["tenant_id"] == b["tenant_id"]
    mine = client.get("/v1/auth/me", headers=auth(joined.json())).json()
    assert mine["role"] == "operator"
    tenants = client.get("/v1/tenants/mine", headers=auth(joined.json())).json()
    assert len(tenants) == 2
    back = client.post("/v1/auth/switch-tenant", headers=auth(joined.json()), json={"tenant_id": a["tenant_id"]})
    assert back.status_code == 200 and back.json()["tenant_id"] == a["tenant_id"]
    # Cannot switch into an org you don't belong to.
    c = register(client, org="Org C")
    r = client.post("/v1/auth/switch-tenant", headers=auth(back.json()), json={"tenant_id": c["tenant_id"]})
    assert r.status_code == 401


def test_invitation_token_single_use(client):
    owner = register(client)
    inv = client.post("/v1/invitations", headers=auth(owner), json={"email": "once@example.com", "role": "viewer"})
    token = inv.json()["accept_url"].split("token=")[1]
    body = {"token": token, "display_name": "Once", "password": PASSWORD}
    assert client.post("/v1/invitations/accept-new", json=body).status_code == 201
    assert client.post("/v1/invitations/accept-new", json=body).status_code == 404


def _mfa_login(client, t):
    secret = client.post("/v1/auth/mfa/enroll", headers=auth(t)).json()["secret"]
    client.post("/v1/auth/mfa/verify", headers=auth(t), json={"code": pyotp.TOTP(secret).now()})
    r = client.post(
        "/v1/auth/login", json={"email": t["email"], "password": PASSWORD, "mfa_code": pyotp.TOTP(secret).now()}
    )
    return r.json()


def test_platform_admin_requires_flag_and_mfa(client, owner_engine):
    staff = register(client, org="Xplosys Ops")
    customer = register(client, org="Customer")
    assert client.get("/admin/v1/tenants", headers=auth(staff)).status_code == 403
    with owner_engine.begin() as c:
        c.execute(text("update users set is_platform_admin = true where email = :e"), {"e": staff["email"]})
    assert client.get("/admin/v1/tenants", headers=auth(staff)).status_code == 403  # no MFA yet
    mfa = _mfa_login(client, staff)
    rows = client.get("/admin/v1/tenants", headers=auth(mfa)).json()
    assert {r["name"] for r in rows} == {"Xplosys Ops", "Customer"}
    r = client.post(
        f"/admin/v1/tenants/{customer['tenant_id']}/suspend", headers=auth(mfa), json={"reason": "Fraud investigation"}
    )
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    # Suspension ends the customer's sessions and blocks login.
    assert client.get("/v1/auth/me", headers=auth(customer)).status_code in (401, 403)
    assert client.post("/v1/auth/login", json={"email": customer["email"], "password": PASSWORD}).status_code == 401


def test_password_change_revokes_sessions_in_every_org(client):
    a = register(client, org="Org A")
    b = register(client, org="Org B")
    inv = client.post("/v1/invitations", headers=auth(b), json={"email": a["email"], "role": "operator"})
    token = inv.json()["accept_url"].split("token=")[1]
    in_b = client.post("/v1/invitations/accept", headers=auth(a), json={"token": token}).json()
    in_a = client.post(
        "/v1/auth/login", json={"email": a["email"], "password": PASSWORD, "tenant_id": a["tenant_id"]}
    ).json()
    r = client.post(
        "/v1/auth/password",
        headers=auth(in_a),
        json={"current_password": PASSWORD, "new_password": "N3w-Str0ng-Passw0rd!"},
    )
    assert r.status_code == 204
    assert client.get("/v1/auth/me", headers=auth(in_b)).status_code == 401
    assert client.post("/v1/auth/refresh", json={"refresh_token": in_b["refresh_token"]}).status_code == 401
