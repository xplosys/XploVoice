# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 2 acceptance tests: routing, failover, circuit breaker, metering in provider units, idempotency,
customer-owned keys, isolation and permissions. Mock provider and MockTransport only; synthetic data."""

import base64
import io
import json
import os
import uuid
import wave

import httpx
import pytest
from sqlalchemy import create_engine, text

from xplovoice_api.core.config import get_settings
from xplovoice_api.modules.m03_ai.adapters import base, mock

from .conftest import PASSWORD, auth, register
from .test_tenancy import _mfa_login, invite_and_join


@pytest.fixture(autouse=True)
def reset_ai():
    s = get_settings()
    saved = dict(s.provider_keys)
    mock.FAIL.clear()
    yield
    mock.FAIL.clear()
    s.provider_keys.clear()
    s.provider_keys.update(saved)
    base.set_transport(None)


def model_id(owner_engine, provider: str, key: str) -> str:
    with owner_engine.connect() as c:
        return str(
            c.execute(
                text(
                    "select m.id from ai_models m join ai_providers p on p.id = m.provider_id "
                    "where p.key=:p and m.model_key=:k"
                ),
                {"p": provider, "k": key},
            ).scalar_one()
        )


def add_model(owner_engine, provider: str, kind: str, key: str, languages=("en-US", "hi-IN"), streaming=True) -> str:
    with owner_engine.begin() as c:
        c.execute(text("select set_config('app.platform_admin','on',true)"))
        c.execute(text("update ai_providers set managed_available = true where key = :p"), {"p": provider})
        return str(
            c.execute(
                text(
                    "insert into ai_models (provider_id, kind, model_key, display_name, languages, streaming) "
                    "select id, :kind, :k, :k, :langs, :st from ai_providers where key = :p "
                    "on conflict (provider_id, kind, model_key) do update set languages = excluded.languages "
                    "returning id"
                ),
                {"p": provider, "kind": kind, "k": key, "langs": list(languages), "st": streaming},
            ).scalar_one()
        )


def set_routes(client, tok, kind, routes):
    return client.put(f"/v1/ai/routes/{kind}", headers=auth(tok), json={"routes": routes})


def mock_routes(client, tok, owner_engine):
    for kind, key in (("llm", "mock-chat"), ("stt", "mock-stt"), ("tts", "mock-tts")):
        r = set_routes(client, tok, kind, [{"model_id": model_id(owner_engine, "mock", key)}])
        assert r.status_code == 200, r.text


def wav_b64(seconds=2.0) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return base64.b64encode(buf.getvalue()).decode()


def usage(owner_engine, tenant_id):
    with owner_engine.begin() as c:
        c.execute(text("select set_config('app.platform_admin','on',true)"))
        return c.execute(
            text(
                "select u.unit, u.quantity, u.account, l.amount, l.currency, l.borne_by, l.priced from usage_events u "
                "join provider_cost_ledger l on l.usage_event_id = u.id where u.tenant_id = :t order by u.id"
            ),
            {"t": tenant_id},
        ).all()


def test_catalog_marks_unconfigured_providers_awaiting_configuration(client):
    t = register(client)
    cat = {p["key"]: p for p in client.get("/v1/ai/catalog", headers=auth(t)).json()}
    assert cat["openai"]["managed_status"].startswith("awaiting configuration")
    assert cat["ollama"]["managed_status"] == "awaiting configuration"
    assert cat["mock"]["managed_status"] == "development only"
    assert cat["openai"]["models"] == []  # no commercial models or prices are invented


def test_no_route_means_clear_503_not_a_fake_answer(client):
    t = register(client)
    r = client.post("/v1/ai/test/chat", headers=auth(t), json={"prompt": "hello"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "no_provider_available"


def test_chat_tts_stt_metered_in_provider_units_with_cost(client, owner_engine):
    t = register(client)
    mock_routes(client, t, owner_engine)
    r = client.post("/v1/ai/test/chat", headers=auth(t), json={"prompt": "Book a cleaning for Friday"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Book a cleaning" in body["text"] and body["units"]["input_token"] > 0 and body["account"] == "managed"
    tts = client.post("/v1/ai/test/speech", headers=auth(t), json={"text": "Your appointment is confirmed"}).json()
    assert tts["mime"] == "audio/wav" and tts["units"] == {"character": len("Your appointment is confirmed")}
    stt = client.post("/v1/ai/test/transcribe", headers=auth(t), json={"audio_base64": wav_b64(2.0)}).json()
    assert stt["units"] == {"audio_second": 2.0}
    rows = usage(owner_engine, t["tenant_id"])
    assert {r.unit for r in rows} == {"input_token", "output_token", "character", "audio_second"}
    assert all(r.priced and r.currency == "USD" and r.borne_by == "platform" for r in rows)
    audio = next(r for r in rows if r.unit == "audio_second")
    assert float(audio.amount) == pytest.approx(2.0 * 0.0001)
    summary = client.get("/v1/usage/summary", headers=auth(t)).json()
    assert {s["unit"] for s in summary} == {"input_token", "output_token", "character", "audio_second"}


def test_usage_is_idempotent_per_key(client, owner_engine):
    t = register(client)
    mock_routes(client, t, owner_engine)
    h = {**auth(t), "Idempotency-Key": "retry-" + uuid.uuid4().hex}
    for _ in range(2):
        assert client.post("/v1/ai/test/speech", headers=h, json={"text": "hello"}).status_code == 200
    assert len(usage(owner_engine, t["tenant_id"])) == 1


def test_failover_to_next_provider_and_breaker_opens(client, owner_engine):
    t = register(client)
    get_settings().provider_keys["openai"] = "sk-test-managed"
    calls = []

    def down(request):
        calls.append(request)
        return httpx.Response(503)

    base.set_transport(httpx.MockTransport(down))
    primary = add_model(owner_engine, "openai", "llm", "test-gpt")
    r = set_routes(client, t, "llm", [{"model_id": primary}, {"model_id": model_id(owner_engine, "mock", "mock-chat")}])
    assert r.status_code == 200, r.text
    out = client.post("/v1/ai/test/chat", headers=auth(t), json={"prompt": "hi"}).json()
    assert out["provider"].startswith("Mock")
    assert [a["outcome"] for a in out["attempts"]] == ["error", "error", "success"]  # one retry, then failover
    # Usage is recorded only for the call that succeeded.
    assert {r.unit for r in usage(owner_engine, t["tenant_id"])} == {"input_token", "output_token"}
    for _ in range(2):  # reach the failure threshold (5)
        client.post("/v1/ai/test/chat", headers=auth(t), json={"prompt": "hi"})
    before = len(calls)
    check = client.get("/v1/ai/routes/llm/check", headers=auth(t)).json()
    assert any("circuit open" in s["reason"] for s in check["skipped"])
    client.post("/v1/ai/test/chat", headers=auth(t), json={"prompt": "hi"})
    assert len(calls) == before  # open breaker: the failing provider is not called at all


def test_language_and_capability_filters_explain_skips(client, owner_engine):
    t = register(client)
    mock_routes(client, t, owner_engine)
    check = client.get("/v1/ai/routes/stt/check", params={"language": "ta-IN"}, headers=auth(t)).json()
    assert check["usable"] == [] and "does not support ta-IN" in check["skipped"][0]["reason"]
    check = client.get("/v1/ai/routes/stt/check", params={"language": "hi-IN"}, headers=auth(t)).json()
    assert len(check["usable"]) == 1


def test_customer_key_is_encrypted_never_returned_and_cost_borne_by_customer(client, owner_engine):
    t = register(client)
    secret = "sk-customer-" + uuid.uuid4().hex
    r = client.post(
        "/v1/ai/credentials", headers=auth(t), json={"provider_key": "openai", "label": "Our OpenAI", "secret": secret}
    )
    assert r.status_code == 201 and secret not in r.text and r.json()["secret_hint"] == "…" + secret[-4:]
    cred = r.json()["id"]
    listing = client.get("/v1/ai/credentials", headers=auth(t))
    assert secret not in listing.text
    with owner_engine.connect() as c:
        stored = c.execute(text("select secret_enc from ai_credentials")).all()  # owner sees nothing: FORCE RLS
        assert stored == []
    with owner_engine.begin() as c:
        c.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": t["tenant_id"]})
        enc = c.execute(text("select secret_enc from ai_credentials")).scalar_one()
        audit_dump = json.dumps([list(x) for x in c.execute(text("select * from audit_log")).all()], default=str)
    assert secret not in enc and secret not in audit_dump

    seen = []

    def ok(request):
        seen.append(request)
        return httpx.Response(
            200,
            content=(
                "data: " + json.dumps({"choices": [{"delta": {"content": "from your key"}}]}) + "\n\n"
                "data: " + json.dumps({"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 3}}) + "\n\n"
                "data: [DONE]\n\n"
            ).encode(),
        )

    base.set_transport(httpx.MockTransport(ok))
    m = add_model(owner_engine, "openai", "llm", "test-gpt")
    assert set_routes(client, t, "llm", [{"model_id": m, "credential_id": cred}]).status_code == 200
    out = client.post("/v1/ai/test/chat", headers=auth(t), json={"prompt": "hi"}).json()
    assert out["account"] == "customer" and out["text"] == "from your key"
    assert seen[0].headers["authorization"] == f"Bearer {secret}"
    rows = usage(owner_engine, t["tenant_id"])
    assert all(r.borne_by == "customer" and r.account == "customer" for r in rows)
    assert all(not r.priced for r in rows)  # no rate card for this model: recorded, not invented

    assert client.delete(f"/v1/ai/credentials/{cred}", headers=auth(t)).status_code == 204
    check = client.get("/v1/ai/routes/llm/check", headers=auth(t)).json()
    assert check["usable"] == [] and "revoked" in check["skipped"][0]["reason"]


def test_other_tenants_keys_and_usage_are_invisible(client, owner_engine):
    a = register(client, org="A")
    b = register(client, org="B")
    cred = client.post(
        "/v1/ai/credentials",
        headers=auth(a),
        json={"provider_key": "openai", "label": "A key", "secret": "sk-aaaaaaaaaaaa"},
    ).json()["id"]
    m = add_model(owner_engine, "openai", "llm", "test-gpt")
    r = set_routes(client, b, "llm", [{"model_id": m, "credential_id": cred}])
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_credential"
    assert client.post(f"/v1/ai/credentials/{cred}/verify", headers=auth(b)).status_code == 404
    assert client.delete(f"/v1/ai/credentials/{cred}", headers=auth(b)).status_code == 404
    assert client.get("/v1/ai/credentials", headers=auth(b)).json() == []
    mock_routes(client, a, owner_engine)
    client.post("/v1/ai/test/speech", headers=auth(a), json={"text": "private"})
    assert client.get("/v1/usage/events", headers=auth(b)).json() == []
    assert len(client.get("/v1/usage/events", headers=auth(a)).json()) == 1


def test_runtime_role_cannot_write_catalog_or_rewrite_usage(client, owner_engine):
    t = register(client)
    mock_routes(client, t, owner_engine)
    client.post("/v1/ai/test/speech", headers=auth(t), json={"text": "hello"})
    app = create_engine(os.environ["XV_DATABASE_URL"])
    try:
        with app.connect() as c:
            with pytest.raises(Exception, match="row-level security"):
                c.execute(
                    text(
                        "insert into ai_providers (key, name, adapter, hosting, kinds) "
                        "values ('evil', 'Evil', 'openai', 'cloud', array['llm'])"
                    )
                )
            c.rollback()
            c.execute(text("select set_config('app.tenant_id', :t, false)"), {"t": t["tenant_id"]})
            with pytest.raises(Exception, match="permission denied"):
                c.execute(text("update usage_events set quantity = 0"))
            c.rollback()
            with pytest.raises(Exception, match="permission denied"):
                c.execute(text("delete from provider_cost_ledger"))
            c.rollback()
    finally:
        app.dispose()


def test_roles_limit_who_configures_and_tests(client, owner_engine):
    owner = register(client)
    viewer = invite_and_join(client, owner, "viewer")
    designer = invite_and_join(client, owner, "agent_designer")
    mock_routes(client, owner, owner_engine)
    mid = model_id(owner_engine, "mock", "mock-chat")
    assert set_routes(client, viewer, "llm", [{"model_id": mid}]).status_code == 403
    assert client.post("/v1/ai/test/chat", headers=auth(viewer), json={"prompt": "x"}).status_code == 403
    assert client.get("/v1/usage/summary", headers=auth(viewer)).status_code == 403
    assert client.get("/v1/ai/routes", headers=auth(viewer)).status_code == 200
    assert client.post("/v1/ai/test/chat", headers=auth(designer), json={"prompt": "x"}).status_code == 200
    assert set_routes(client, designer, "llm", [{"model_id": mid}]).status_code == 403


def test_admin_catalog_management_requires_mfa_admin_and_baa_for_phi(client, owner_engine):
    staff = register(client, org="Xplosys Ops")
    with owner_engine.begin() as c:
        c.execute(text("update users set is_platform_admin = true where email = :e"), {"e": staff["email"]})
    assert client.get("/admin/v1/ai/providers", headers=auth(staff)).status_code == 403  # no MFA session
    adm = _mfa_login(client, staff)
    providers = {p["key"]: p for p in client.get("/admin/v1/ai/providers", headers=auth(adm)).json()}
    oa = providers["openai"]
    assert oa["managed_key_configured"] is False and oa["health"]["state"] == "closed"
    r = client.patch(
        f"/admin/v1/ai/providers/{oa['id']}",
        headers=auth(adm),
        json={"phi_eligible": True, "reason": "testing BAA rule"},
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "baa_required"
    m = client.post(
        "/admin/v1/ai/models",
        headers=auth(adm),
        json={
            "provider_id": oa["id"],
            "kind": "llm",
            "model_key": "example-model",
            "display_name": "Example",
            "languages": ["en-US", "hi-IN"],
            "streaming": True,
            "reason": "Catalog setup for test",
        },
    )
    assert m.status_code == 201, m.text
    rc = client.post(
        "/admin/v1/ai/rate-cards",
        headers=auth(adm),
        json={
            "model_id": m.json()["id"],
            "unit": "input_token",
            "unit_price": "0.0000025",
            "currency": "USD",
            "source": "Synthetic test price",
            "reason": "Catalog setup for test",
        },
    )
    assert rc.status_code == 201, rc.text
    pr = client.put(
        "/admin/v1/ai/routes/llm", headers=auth(adm), json={"model_ids": [m.json()["id"]], "reason": "Default for test"}
    )
    assert pr.status_code == 200 and pr.json()["llm"][0]["model"] == "Example"
    # A tenant with no routes of its own inherits the platform default.
    other = register(client, org="Customer")
    routes = {r["kind"]: r for r in client.get("/v1/ai/routes", headers=auth(other)).json()}
    assert routes["llm"]["source"] == "platform default"
    with owner_engine.begin() as c:
        c.execute(text("select set_config('app.platform_admin','on',true)"))
        actions = {r[0] for r in c.execute(text("select action from audit_log where actor_kind='platform_admin'"))}
    assert {"admin.ai_model_added", "admin.ai_rate_card_added", "admin.ai_platform_routes_updated"} <= actions


def test_mock_provider_is_refused_in_production_like_environments(client, owner_engine, monkeypatch):
    from xplovoice_api.modules.m03_ai.models import Provider
    from xplovoice_api.modules.m03_ai.routing import managed_endpoint

    monkeypatch.setattr(get_settings(), "environment", "production")
    ep, why = managed_endpoint(Provider(key="mock", hosting="dev_only"))
    assert ep is None and why == "development-only provider"


_ = PASSWORD
