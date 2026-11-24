# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import pyotp
from sqlalchemy import text

from .conftest import PASSWORD, auth, register


def test_register_creates_owner_with_country_defaults(client):
    t = register(client, country="IN")
    me = client.get("/v1/auth/me", headers=auth(t)).json()
    assert me["role"] == "owner"
    tenant = client.get("/v1/tenants/current", headers=auth(t)).json()
    assert (tenant["currency"], tenant["timezone"], tenant["default_language"]) == ("INR", "Asia/Kolkata", "hi-IN")
    us = register(client, country="US")
    tenant = client.get("/v1/tenants/current", headers=auth(us)).json()
    assert (tenant["currency"], tenant["date_format"]) == ("USD", "MM/DD/YYYY")


def test_weak_password_rejected(client):
    r = client.post(
        "/v1/auth/register",
        json={
            "email": "a@example.com",
            "password": "short",
            "display_name": "A",
            "organization_name": "A",
            "country_code": "US",
        },
    )
    assert r.status_code == 422


def test_password_is_argon2id(client, owner_engine):
    t = register(client)
    with owner_engine.connect() as c:
        h = c.execute(text("select password_hash from users where email = :e"), {"e": t["email"]}).scalar()
    assert h.startswith("$argon2id$")


def test_login_and_wrong_password(client):
    t = register(client)
    assert client.post("/v1/auth/login", json={"email": t["email"], "password": PASSWORD}).status_code == 200
    r = client.post("/v1/auth/login", json={"email": t["email"], "password": "Wrong-Passw0rd!"})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "invalid_credentials"
    r = client.post("/v1/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "invalid_credentials"


def test_lockout_after_repeated_failures(client):
    t = register(client)
    for _ in range(5):
        client.post("/v1/auth/login", json={"email": t["email"], "password": "Wrong-Passw0rd!"})
    r = client.post("/v1/auth/login", json={"email": t["email"], "password": PASSWORD})
    assert r.status_code == 401  # locked even with the right password


def test_refresh_rotation_and_reuse_detection(client):
    t = register(client)
    r1 = client.post("/v1/auth/refresh", json={"refresh_token": t["refresh_token"]})
    assert r1.status_code == 200
    new = r1.json()
    assert new["refresh_token"] != t["refresh_token"]
    # Replaying the old token revokes the whole family, including the new one.
    r2 = client.post("/v1/auth/refresh", json={"refresh_token": t["refresh_token"]})
    assert r2.status_code == 401 and r2.json()["detail"]["code"] == "refresh_reused"
    assert client.post("/v1/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 401
    assert client.get("/v1/auth/me", headers=auth(new)).status_code == 401


def test_logout_revokes_access_immediately(client):
    t = register(client)
    assert client.post("/v1/auth/logout", headers=auth(t)).status_code == 204
    assert client.get("/v1/auth/me", headers=auth(t)).status_code == 401


def test_mfa_enroll_and_login(client):
    t = register(client)
    enroll = client.post("/v1/auth/mfa/enroll", headers=auth(t)).json()
    totp = pyotp.TOTP(enroll["secret"])
    assert client.post("/v1/auth/mfa/verify", headers=auth(t), json={"code": totp.now()}).status_code == 204
    r = client.post("/v1/auth/login", json={"email": t["email"], "password": PASSWORD})
    assert r.json()["detail"]["code"] == "mfa_required"
    r = client.post("/v1/auth/login", json={"email": t["email"], "password": PASSWORD, "mfa_code": "000000"})
    assert r.status_code == 401
    r = client.post("/v1/auth/login", json={"email": t["email"], "password": PASSWORD, "mfa_code": totp.now()})
    assert r.status_code == 200


def test_mfa_secret_encrypted_at_rest(client, owner_engine):
    t = register(client)
    secret = client.post("/v1/auth/mfa/enroll", headers=auth(t)).json()["secret"]
    with owner_engine.connect() as c:
        stored = c.execute(text("select mfa_secret_enc from users where email = :e"), {"e": t["email"]}).scalar()
    assert stored and secret not in stored


def test_tampered_token_rejected(client):
    t = register(client)
    bad = t["access_token"][:-4] + "abcd"
    assert client.get("/v1/auth/me", headers={"Authorization": f"Bearer {bad}"}).status_code == 401
    assert client.get("/v1/auth/me").status_code == 401


def test_password_change_revokes_sessions(client):
    t = register(client)
    r = client.post(
        "/v1/auth/password", headers=auth(t), json={"current_password": PASSWORD, "new_password": "An0ther-Str0ng-Pass"}
    )
    assert r.status_code == 204
    assert client.get("/v1/auth/me", headers=auth(t)).status_code == 401
    assert (
        client.post("/v1/auth/login", json={"email": t["email"], "password": "An0ther-Str0ng-Pass"}).status_code == 200
    )


def test_audit_never_contains_secrets(client, owner_engine):
    t = register(client)
    client.post("/v1/auth/login", json={"email": t["email"], "password": PASSWORD})
    with owner_engine.connect() as c:
        c.execute(text("select set_config('app.platform_admin', 'on', false)"))
        blob = c.execute(text("select string_agg(metadata::text || coalesce(reason,''), ' ') from audit_log")).scalar()
    assert PASSWORD not in blob and t["refresh_token"] not in blob
