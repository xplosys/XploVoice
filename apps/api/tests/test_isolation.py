# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Cross-tenant isolation suite (ADD-O16, HC-004/HC-005 pattern). Runs against the real runtime role."""

import os

import pytest
from sqlalchemy import create_engine, text

from .conftest import auth, register


@pytest.fixture
def app_engine():
    eng = create_engine(os.environ["XV_DATABASE_URL"])
    yield eng
    eng.dispose()


def test_runtime_role_cannot_bypass_rls(app_engine):
    with app_engine.connect() as c:
        row = c.execute(text("select rolsuper, rolbypassrls from pg_roles where rolname = current_user")).one()
    assert row == (False, False)


def test_every_tenant_table_has_forced_rls(owner_engine):
    with owner_engine.connect() as c:
        rows = c.execute(
            text("""
            select c.relname, c.relrowsecurity, c.relforcerowsecurity
            from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind = 'r'
              and (exists (select 1 from information_schema.columns col
                           where col.table_schema = 'public' and col.table_name = c.relname
                             and col.column_name = 'tenant_id')
                   or c.relname = 'tenants')""")
        ).all()
    assert rows, "no tenant tables found"
    missing = [r.relname for r in rows if not (r.relrowsecurity and r.relforcerowsecurity)]
    assert missing == [], f"tables without ENABLE+FORCE RLS: {missing}"


def test_sql_level_isolation(client, app_engine):
    a = register(client, org="Tenant A")
    b = register(client, org="Tenant B")
    with app_engine.begin() as c:
        c.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": a["tenant_id"]})
        names = {r[0] for r in c.execute(text("select name from tenants"))}
        members = c.execute(text("select distinct tenant_id::text from tenant_memberships")).scalars().all()
        audit = c.execute(text("select distinct tenant_id::text from audit_log")).scalars().all()
        # Writes into another tenant are rejected by the policy's WITH CHECK.
        with pytest.raises(Exception, match="row-level security"):
            c.execute(
                text(
                    "insert into tenant_memberships (tenant_id, user_id, role) "
                    "select :b, id, 'owner' from users limit 1"
                ),
                {"b": b["tenant_id"]},
            )
    assert names == {"Tenant A"}
    assert members == [a["tenant_id"]]
    assert set(audit) <= {a["tenant_id"]}


def test_no_context_sees_nothing(client, app_engine):
    register(client)
    with app_engine.connect() as c:
        assert c.execute(text("select count(*) from tenants")).scalar() == 0
        assert c.execute(text("select count(*) from tenant_memberships")).scalar() == 0
        assert c.execute(text("select count(*) from audit_log")).scalar() == 0
        assert c.execute(text("select count(*) from refresh_tokens")).scalar() == 0


def test_audit_log_is_append_only_for_runtime_role(client, app_engine):
    a = register(client)
    with app_engine.connect() as c:
        c.execute(text("select set_config('app.tenant_id', :t, false)"), {"t": a["tenant_id"]})
        for stmt in ("update audit_log set action = 'x'", "delete from audit_log"):
            with pytest.raises(Exception, match="permission denied"):
                c.execute(text(stmt))
            c.rollback()
            c.execute(text("select set_config('app.tenant_id', :t, false)"), {"t": a["tenant_id"]})


def test_audit_hash_chain_links(client, owner_engine):
    a = register(client)
    client.post("/v1/auth/logout", headers=auth(a))
    with owner_engine.connect() as c:
        c.execute(text("select set_config('app.platform_admin', 'on', false)"))
        rows = c.execute(
            text("select prev_hash, event_hash from audit_log where tenant_id = :t order by id"), {"t": a["tenant_id"]}
        ).all()
    assert len(rows) >= 2 and rows[0].prev_hash is None
    for prev, cur in zip(rows, rows[1:], strict=False):
        assert cur.prev_hash == prev.event_hash


def test_api_cannot_reach_other_tenant_resources(client):
    a = register(client, org="Tenant A")
    b = register(client, org="Tenant B")
    b_member = client.get("/v1/members", headers=auth(b)).json()[0]["id"]
    # IDOR attempts with a valid id from another tenant look exactly like a missing resource.
    assert client.patch(f"/v1/members/{b_member}", headers=auth(a), json={"role": "viewer"}).status_code == 404
    assert client.delete(f"/v1/members/{b_member}", headers=auth(a)).status_code == 404
    inv = client.post("/v1/invitations", headers=auth(b), json={"email": "z@example.com", "role": "viewer"}).json()
    assert client.delete(f"/v1/invitations/{inv['id']}", headers=auth(a)).status_code == 404
    assert all(m["id"] != b_member for m in client.get("/v1/members", headers=auth(a)).json())
    audit_a = client.get("/v1/audit-logs", headers=auth(a)).json()
    assert audit_a and all(e["resource_id"] != b["tenant_id"] for e in audit_a)


def test_member_of_two_orgs_sees_only_current_org(client):
    a = register(client, org="Tenant A")
    b = register(client, org="Tenant B")
    inv = client.post("/v1/invitations", headers=auth(b), json={"email": a["email"], "role": "viewer"}).json()
    client.post("/v1/invitations/accept", headers=auth(a), json={"token": inv["accept_url"].split("token=")[1]})
    # a's original session (tenant A) must not list tenant B's members, even though a is a member of B.
    roles = [m["role"] for m in client.get("/v1/members", headers=auth(a)).json()]
    assert roles == ["owner"]


def test_tenant_id_in_body_is_ignored(client):
    a = register(client, org="Tenant A")
    b = register(client, org="Tenant B")
    r = client.patch("/v1/tenants/current", headers=auth(a), json={"name": "Renamed", "id": b["tenant_id"]})
    assert r.status_code == 200 and r.json()["id"] == a["tenant_id"]
    assert client.get("/v1/tenants/current", headers=auth(b)).json()["name"] == "Tenant B"


def test_revoke_my_sessions_cannot_target_another_user(client, app_engine):
    victim = register(client, org="Victim")
    attacker = register(client, org="Attacker")
    with app_engine.begin() as c:
        me = client.get("/v1/auth/me", headers=auth(attacker)).json()["user_id"]
        vic = client.get("/v1/auth/me", headers=auth(victim)).json()["user_id"]
        c.execute(text("select set_config('app.user_id', :u, true)"), {"u": me})
        assert c.execute(text("select revoke_my_sessions(:v)"), {"v": vic}).scalar_one() == 0
    assert client.get("/v1/auth/me", headers=auth(victim)).status_code == 200
