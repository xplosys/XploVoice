# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 3 latency benchmark (CR-004, first run).

Drives synthetic calls through the real API, Redis dispatch and voice-worker processes at real-time speed and
reports per-stage latency from the timings each call stores. Development only: it uses the mock provider and
the scripted (synthetic audio) caller, so it measures XploVoice's own pipeline overhead plus end-of-turn
detection, NOT real STT, LLM or TTS vendors. Vendor latency is measured once vendor accounts exist.

Usage (API already running in development at --api):
    python scripts/voice_benchmark.py --api http://localhost:8000 --levels 1,10,20 --out bench.md
"""

import argparse
import os
import statistics
import subprocess
import sys
import time
import uuid

import httpx

TURN = "tone:1000,silence:6000"  # longer than the mock reply, so turns are not barged in


def pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    v = sorted(values)
    k = max(0, min(len(v) - 1, int(round(p / 100 * (len(v) - 1)))))
    return v[k]


def setup(api: str) -> tuple[dict, str]:
    email = f"bench-{uuid.uuid4().hex[:8]}@example.com"
    r = httpx.post(
        f"{api}/v1/auth/register",
        json={
            "email": email,
            "password": "Bench-Passw0rd-123!",
            "display_name": "Benchmark",
            "organization_name": "Benchmark Clinic (synthetic)",
            "country_code": "IN",
        },
    )
    r.raise_for_status()
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    cat = httpx.get(f"{api}/v1/ai/catalog", headers=h).json()
    for kind, key in (("llm", "mock-chat"), ("stt", "mock-stt"), ("tts", "mock-tts")):
        mid = next(m["id"] for p in cat for m in p["models"] if m["model_key"] == key)
        httpx.put(f"{api}/v1/ai/routes/{kind}", headers=h, json={"routes": [{"model_id": mid}]}).raise_for_status()
    agent = httpx.post(
        f"{api}/v1/agents",
        headers=h,
        json={
            "name": "Benchmark agent",
            "config": {"greeting": "Hello.", "interruption": {"endpoint_silence_ms": 500}},
        },
    )
    agent.raise_for_status()
    return h, agent.json()["id"]


def run_level(api: str, h: dict, agent_id: str, n: int, turns: int) -> list[dict]:
    ids = []
    for _ in range(n):
        r = httpx.post(f"{api}/v1/voice/sessions", headers=h, json={"agent_id": agent_id})
        r.raise_for_status()
        ids.append(r.json()["call_id"])
    deadline = time.time() + 30 + turns * 9
    calls: list[dict] = []
    while time.time() < deadline:
        calls = [httpx.get(f"{api}/v1/calls/{i}", headers=h).json() for i in ids]
        if all(c["status"] in ("completed", "failed", "abandoned") for c in calls):
            break
        time.sleep(1)
    return calls


def summarise(calls: list[dict]) -> dict:
    stage: dict[str, list[float]] = {}
    for c in calls:
        for e in c["events"]:
            d = e["data"]
            if e["type"] != "turn.metrics" or d.get("kind") != "reply" or d.get("interrupted"):
                continue
            for k in ("endpoint_ms", "stt_ms", "llm_first_token_ms", "tts_first_audio_ms", "first_audible_ms"):
                if k in d:
                    stage.setdefault(k, []).append(d[k])
            if "first_audible_ms" in d and "endpoint_ms" in d:
                stage.setdefault("overhead_after_endpoint_ms", []).append(d["first_audible_ms"] - d["endpoint_ms"])
    ok = sum(c["status"] == "completed" for c in calls)
    return {"calls": len(calls), "completed": ok, "stage": stage}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--levels", default="1,10,20")
    ap.add_argument("--turns", type=int, default=3)
    ap.add_argument("--out", default="voice-benchmark.md")
    a = ap.parse_args()
    if os.environ.get("XV_ENVIRONMENT", "development") not in ("development", "test"):
        raise SystemExit("development only")
    levels = [int(x) for x in a.levels.split(",")]
    script = ",".join(["silence:2000"] + [TURN] * a.turns + ["silence:1000"])
    env = os.environ | {
        "XV_INTERNAL_API_URL": a.api,
        "XV_WORKER_CHANNEL": "scripted",
        "XV_WORKER_SCRIPT": script,
        "XV_WORKER_SPEED": "1",
        "XV_WORKER_MAX_CALLS": str(max(levels)),
        "XV_WORKER_METRICS_PORT": "0",
        "XV_LOG_LEVEL": "WARNING",
    }
    worker = subprocess.Popen([sys.executable, "-m", "xplovoice_worker"], env=env)  # noqa: S603
    try:
        h, agent_id = setup(a.api)
        rows = []
        for n in levels:
            s = summarise(run_level(a.api, h, agent_id, n, a.turns))
            rows.append((n, s))
            print(f"{n} concurrent: {s['completed']}/{s['calls']} completed")
    finally:
        worker.terminate()
        worker.wait(30)
    keys = [
        ("endpoint_ms", "End-of-turn wait (configured 500 ms silence)"),
        ("stt_ms", "STT request (mock)"),
        ("llm_first_token_ms", "LLM first token (mock)"),
        ("tts_first_audio_ms", "TTS first clause (mock)"),
        ("overhead_after_endpoint_ms", "Pipeline after end-of-turn"),
        ("first_audible_ms", "First audible response (from end of caller speech)"),
    ]
    lines = [
        "| Concurrent calls per worker | Completed | Turns measured | Stage | p50 ms | p95 ms | max ms |",
        "|---|---|---|---|---|---|---|",
    ]
    for n, s in rows:
        measured = len(s["stage"].get("first_audible_ms", []))
        for k, label in keys:
            v = s["stage"].get(k, [])
            lines.append(
                f"| {n} | {s['completed']}/{s['calls']} | {measured} | {label} | "
                f"{statistics.median(v):.0f} | {pct(v, 95):.0f} | {max(v):.0f} |"
                if v
                else f"| {n} | {s['completed']}/{s['calls']} | {measured} | {label} | - | - | - |"
            )
    with open(a.out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
