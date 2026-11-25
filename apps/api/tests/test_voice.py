# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 3 acceptance: agents pin versions, browser voice sessions, the worker-only internal API, a full call
through the real API and AI gateway (mock provider, synthetic audio), and isolation of calls between tenants."""

import asyncio
import time
import uuid

import httpx
import jwt
import pytest
from sqlalchemy import text

from xplovoice_api.core.config import get_settings
from xplovoice_api.main import create_app
from xplovoice_api.modules.m03_ai.adapters import mock
from xplovoice_api.modules.m08_calls.dispatch import STREAM
from xplovoice_engine.audio import silence, tone
from xplovoice_engine.backend import HttpBackend
from xplovoice_engine.channel import ScriptedChannel
from xplovoice_engine.session import CallSession

from .conftest import auth, register
from .test_ai import mock_routes
from .test_tenancy import invite_and_join

WK = {"X-Worker-Key": "dev-only-worker-key"}


@pytest.fixture(autouse=True)
def _reset():
    mock.FAIL.clear()
    yield
    mock.FAIL.clear()


def make_agent(client, tok, **cfg):
    body = {"name": "Front desk", "config": {"greeting": "Hello, Sunrise Dental.", "endpoint_silence_ms": 500} | cfg}
    r = client.post("/v1/agents", headers=auth(tok), json=body)
    assert r.status_code == 201, r.text
    return r.json()


def start(client, tok, agent_id):
    return client.post("/v1/voice/sessions", headers=auth(tok), json={"agent_id": agent_id})


def job_token(r, call_id: str) -> str:
    for _id, fields in r.xrange(STREAM):
        if fields[b"call_id"].decode() == call_id:
            return fields[b"token"].decode()
    raise AssertionError("no job dispatched")


@pytest.fixture
def redis_client():
    from xplovoice_api.core.ratelimit import client

    return client()


def test_agent_versions_are_immutable_and_calls_pin_them(client, owner_engine):
    t = register(client)
    a = make_agent(client, t)
    assert a["version"] == 1
    upd = client.put(
        f"/v1/agents/{a['id']}", headers=auth(t), json={"name": "Front desk", "config": {"greeting": "Hi!"}}
    )
    assert upd.json()["version"] == 2 and upd.json()["version_id"] != a["version_id"]
    assert [v["version"] for v in client.get(f"/v1/agents/{a['id']}/versions", headers=auth(t)).json()] == [2, 1]
    with owner_engine.connect() as c:
        c.execute(text("select set_config('app.tenant_id', :t, false)"), {"t": t["tenant_id"]})
        perms = c.execute(text("select has_table_privilege('xplovoice_app', 'agent_versions', 'UPDATE')")).scalar_one()
    assert perms is False


def test_voice_session_token_is_scoped_short_lived_and_dispatched(client, redis_client):
    t = register(client)
    a = make_agent(client, t)
    r = start(client, t, a["id"])
    assert r.status_code == 201, r.text
    body = r.json()
    s = get_settings()
    claims = jwt.decode(body["token"], s.livekit_api_secret, algorithms=["HS256"])
    assert claims["video"]["room"] == body["room"] and claims["video"]["canPublishSources"] == ["microphone"]
    assert claims["exp"] - time.time() <= s.voice_token_minutes * 60 + 5
    assert t["tenant_id"] not in body["room"] and a["id"] not in body["room"]  # opaque room name
    call = client.get(f"/v1/calls/{body['call_id']}", headers=auth(t)).json()
    assert call["status"] == "dispatching" and call["agent_version"] == 1 and call["channel"] == "browser"
    assert job_token(redis_client, body["call_id"])


def test_concurrent_call_limit(client):
    t = register(client)
    a = make_agent(client, t)
    assert start(client, t, a["id"]).status_code == 201
    assert start(client, t, a["id"]).status_code == 201
    r = start(client, t, a["id"])
    assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many_calls"


def test_roles_for_calls(client):
    owner = register(client)
    a = make_agent(client, owner)
    viewer = invite_and_join(client, owner, "viewer")
    designer = invite_and_join(client, owner, "agent_designer")
    assert start(client, viewer, a["id"]).status_code == 403
    assert client.post("/v1/agents", headers=auth(viewer), json={"name": "x"}).status_code == 403
    assert client.get("/v1/calls", headers=auth(viewer)).status_code == 200
    assert start(client, designer, a["id"]).status_code == 201


def test_internal_api_requires_worker_key_and_matching_call_token(client, redis_client):
    t = register(client)
    a = make_agent(client, t)
    c1 = start(client, t, a["id"]).json()["call_id"]
    c2 = start(client, t, a["id"]).json()["call_id"]
    tok1 = job_token(redis_client, c1)
    url = f"/internal/v1/calls/{c1}/bootstrap"
    body = {"worker_id": "w1"}
    assert client.post(url, json=body, headers={"Authorization": f"Bearer {tok1}"}).status_code == 401
    assert client.post(url, json=body, headers={**WK, "Authorization": "Bearer nope"}).status_code == 401
    user_token = {**WK, "Authorization": f"Bearer {t['access_token']}"}  # a tenant user token is not enough
    assert client.post(url, json=body, headers=user_token).status_code == 401
    other = f"/internal/v1/calls/{c2}/bootstrap"  # a token for call 1 cannot act on call 2
    assert client.post(other, json=body, headers={**WK, "Authorization": f"Bearer {tok1}"}).status_code == 404
    r = client.post(url, json=body, headers={**WK, "Authorization": f"Bearer {tok1}"})
    assert r.status_code == 200 and r.json()["resumed"] is False
    lk = jwt.decode(r.json()["livekit_token"], get_settings().livekit_api_secret, algorithms=["HS256"])
    assert lk["video"]["room"] == r.json()["room"] and "canPublishSources" not in lk["video"]


def _run_call(client, redis_client, t, agent_id, script, speed=20.0):
    call_id = start(client, t, agent_id).json()["call_id"]
    token = job_token(redis_client, call_id)

    async def go():
        backend = HttpBackend(
            "http://api", WK["X-Worker-Key"], call_id, token, transport=httpx.ASGITransport(app=create_app())
        )
        boot = await backend.bootstrap("test-worker")
        ch = ScriptedChannel(script, speed=speed, tail_ms=1500)
        reason = await CallSession(backend, ch, boot, worker_id="test-worker").run()
        await backend.aclose()
        return reason, ch

    reason, ch = asyncio.run(go())
    return call_id, reason, ch


def test_browser_call_end_to_end_through_api_and_gateway(client, owner_engine, redis_client):
    t = register(client)
    mock_routes(client, t, owner_engine)
    a = make_agent(client, t)
    call_id, reason, ch = _run_call(client, redis_client, t, a["id"], [silence(2000), tone(900), silence(4000)])
    assert reason == "caller_hangup" and len(ch.heard) > 0
    call = client.get(f"/v1/calls/{call_id}", headers=auth(t)).json()
    assert call["status"] == "completed" and call["end_reason"] == "caller_hangup"
    assert call["connected_at"] and call["ended_at"] and float(call["duration_seconds"]) > 0
    lines = [(s["speaker"], s["text"]) for s in call["transcript"]]
    assert lines[0] == ("agent", "Hello, Sunrise Dental.")
    assert lines[1][0] == "caller" and lines[1][1].startswith("[mock transcript")
    assert lines[2][0] == "agent" and "You said" in lines[2][1]
    metrics = [e["data"] for e in call["events"] if e["type"] == "turn.metrics" and e["data"]["kind"] == "reply"]
    assert metrics and "first_audible_ms" in metrics[0] and "stt" in metrics[0]["providers"]
    # Every provider call is metered against the call, in provider units.
    usage = client.get("/v1/usage/events", headers=auth(t)).json()
    mine = [u for u in usage if u["source_type"] == "call"]
    assert {u["unit"] for u in mine} >= {"audio_second", "input_token", "output_token", "character"}
    lst = client.get("/v1/calls", headers=auth(t)).json()
    assert lst[0]["id"] == call_id and lst[0]["agent_name"] == "Front desk"


def test_call_with_no_provider_ends_cleanly_as_failed(client, redis_client):
    t = register(client)  # no routes configured at all
    a = make_agent(client, t)
    call_id, reason, ch = _run_call(client, redis_client, t, a["id"], [silence(3000)])
    assert reason == "no_provider" and len(ch.heard) == 0
    call = client.get(f"/v1/calls/{call_id}", headers=auth(t)).json()
    assert call["status"] == "failed" and call["end_reason"] == "no_provider"


def test_late_or_repeated_state_updates_never_move_a_call_backwards(client, redis_client):
    t = register(client)
    a = make_agent(client, t)
    c = start(client, t, a["id"]).json()["call_id"]
    h = {**WK, "Authorization": f"Bearer {job_token(redis_client, c)}"}
    assert client.post(f"/internal/v1/calls/{c}/state", headers=h, json={"status": "active"}).json()["moved"]
    done = client.post(
        f"/internal/v1/calls/{c}/state", headers=h, json={"status": "completed", "reason": "agent_ended"}
    )
    assert done.json() == {"status": "completed", "moved": True}
    late = client.post(f"/internal/v1/calls/{c}/state", headers=h, json={"status": "active"})
    assert late.json() == {"status": "completed", "moved": False}
    events = client.get(f"/v1/calls/{c}", headers=auth(t)).json()["events"]
    assert [e["type"] for e in events][-1] == "state.ignored"
    # A worker that recovers a finished call is told it has ended.
    assert client.post(f"/internal/v1/calls/{c}/bootstrap", headers=h, json={"worker_id": "w"}).status_code == 409


def test_recording_is_idempotent(client, redis_client):
    t = register(client)
    a = make_agent(client, t)
    c = start(client, t, a["id"]).json()["call_id"]
    h = {**WK, "Authorization": f"Bearer {job_token(redis_client, c)}"}
    body = {
        "events": [{"key": "k1", "type": "turn.metrics", "data": {"turn": 1}}],
        "segments": [{"seq": 0, "speaker": "agent", "text": "Hello."}],
    }
    for _ in range(3):
        assert client.post(f"/internal/v1/calls/{c}/record", headers=h, json=body).status_code == 200
    call = client.get(f"/v1/calls/{c}", headers=auth(t)).json()
    assert len(call["transcript"]) == 1 and sum(e["type"] == "turn.metrics" for e in call["events"]) == 1


def test_calls_are_isolated_between_tenants(client, redis_client):
    a = register(client, org="Tenant A")
    b = register(client, org="Tenant B")
    agent_a = make_agent(client, a)
    c = start(client, a, agent_a["id"]).json()["call_id"]
    assert client.get(f"/v1/calls/{c}", headers=auth(b)).status_code == 404
    assert client.post(f"/v1/calls/{c}/end", headers=auth(b)).status_code == 404
    assert start(client, b, agent_a["id"]).status_code == 404  # cannot call another tenant's agent
    assert client.get("/v1/calls", headers=auth(b)).json() == []
    assert client.get(f"/v1/agents/{agent_a['id']}", headers=auth(b)).status_code == 404


def test_end_call_from_dashboard(client, redis_client):
    t = register(client)
    a = make_agent(client, t)
    c = start(client, t, a["id"]).json()["call_id"]
    assert client.post(f"/v1/calls/{c}/end", headers=auth(t)).status_code == 204
    call = client.get(f"/v1/calls/{c}", headers=auth(t)).json()
    assert call["status"] == "abandoned" and call["end_reason"] == "user_ended"
    assert client.post(f"/v1/calls/{c}/end", headers=auth(t)).status_code == 409


def test_unknown_call_returns_404_for_worker(client):
    fake = str(uuid.uuid4())
    from xplovoice_api.modules.m08_calls.dispatch import worker_call_token

    tok = worker_call_token(tenant_id=uuid.uuid4(), call_id=uuid.UUID(fake), ttl_seconds=60)
    r = client.post(
        f"/internal/v1/calls/{fake}/bootstrap",
        headers={**WK, "Authorization": f"Bearer {tok}"},
        json={"worker_id": "w"},
    )
    assert r.status_code == 404
