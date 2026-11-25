# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 3 gate: kill a voice worker mid-call (SIGKILL, no clean-up) and check another worker takes the call
over and finishes it. Real processes: the API under uvicorn and two workers, talking through Redis and the
internal API. The caller is synthetic audio (the scripted channel, development and test only)."""

import os
import signal
import socket
import subprocess
import sys
import time

import httpx
import pytest

from .conftest import auth, register
from .test_ai import mock_routes

SCRIPT = ",".join(["silence:1500", "tone:800", "silence:2500", "tone:800", "silence:2500", "tone:800", "silence:2500"])


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def api_server():
    port = _free_port()
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, test only
        [sys.executable, "-m", "uvicorn", "xplovoice_api.main:app", "--port", str(port), "--log-level", "warning"],
        env=os.environ.copy(),
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{url}/healthz").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    yield url
    proc.terminate()
    proc.wait(10)


def _worker(api_url: str) -> subprocess.Popen:
    env = os.environ | {
        "XV_INTERNAL_API_URL": api_url,
        "XV_WORKER_CHANNEL": "scripted",
        "XV_WORKER_SCRIPT": SCRIPT,
        "XV_WORKER_SPEED": "4",
        "XV_WORKER_LEASE_SECONDS": "2",
        "XV_WORKER_HEARTBEAT_SECONDS": "0.5",
        "XV_WORKER_METRICS_PORT": "0",
    }
    return subprocess.Popen([sys.executable, "-m", "xplovoice_worker"], env=env)  # noqa: S603


def _wait(pred, timeout: float, what: str):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {what}")


def test_worker_killed_mid_call_is_recovered_by_another_worker(client, owner_engine, api_server):
    t = register(client)
    mock_routes(client, t, owner_engine)
    agent = client.post(
        "/v1/agents", headers=auth(t), json={"name": "Desk", "config": {"interruption": {"endpoint_silence_ms": 500}}}
    )
    a = _worker(api_server)
    b = None
    try:
        call_id = client.post("/v1/voice/sessions", headers=auth(t), json={"agent_id": agent.json()["id"]}).json()[
            "call_id"
        ]

        def detail():
            return client.get(f"/v1/calls/{call_id}", headers=auth(t)).json()

        _wait(lambda: any(s["speaker"] == "caller" for s in detail()["transcript"]), 30, "first caller turn")
        os.kill(a.pid, signal.SIGKILL)  # no clean-up, no ack, no state change
        a.wait(5)
        assert detail()["status"] == "active"
        b = _worker(api_server)
        call = _wait(lambda: (d := detail())["status"] in ("completed", "failed") and d, 60, "call to finish")
    finally:
        for p in (a, b):
            if p and p.poll() is None:
                p.terminate()
                p.wait(10)
    assert call["status"] == "completed" and call["recoveries"] == 1
    types = [e["type"] for e in call["events"]]
    assert "worker.joined" in types and "worker.recovered" in types
    agent_lines = [s["text"] for s in call["transcript"] if s["speaker"] == "agent"]
    assert any(x.startswith("Sorry about that") for x in agent_lines)  # the caller may talk over the rest
    seqs = [s["seq"] for s in call["transcript"]]
    assert seqs == sorted(set(seqs))  # the second worker continued the transcript without collisions
