# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Controlled tool gateway (addendum G). Every tool call an agent makes passes these checks, in order:

1. Authorization: the tool is granted on the call's pinned agent version, enabled in the tenant's tool policy, and
   its prerequisites exist (a booking calendar, an approved message, a connected system).
2. Validation: the arguments match the tool's strict schema (unknown fields are refused).
3. Idempotency: a repeated call with the same key returns the first result and does nothing again.
4. Human approval: a sensitive tool (by default, cancelling an appointment) is held for a person to approve.
5. Execution in its own transaction, with a statement timeout, an overall timeout and one retry on a transient
   database error. The change and its execution record commit together or not at all.
6. Audit: an audit event and an execution record for every outcome, and Prometheus metrics.

Arguments and results are stored on the execution record (tenant-isolated) for staff to review; they are never
written to the audit log or application logs."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from prometheus_client import Counter, Histogram
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ...core import audit
from ...core.config import get_settings
from ...core.db import session_scope, set_context
from ..m03_ai.adapters.base import ToolSpec
from ..m05_agents.schemas import AgentConfig
from ..m11_workflows.service import Actor, WorkflowError
from .models import ToolExecution, ToolPolicy
from .registry import TOOLS, ToolContext, ToolDef, json_schema, unavailable

log = logging.getLogger("xplovoice.tools")
CALLS = Counter("xv_tool_calls_total", "Tool calls by outcome", ["tool", "outcome"])
LATENCY = Histogram("xv_tool_seconds", "Tool execution latency", ["tool"])


@dataclass
class ToolOutcome:
    status: str  # succeeded | failed | rejected | pending_approval | approved | denied
    result: dict[str, Any]  # what the model is told
    execution_id: UUID | None = None


def policy(session: Session, key: str) -> tuple[bool, bool]:
    """(enabled, require_approval) for this tenant; defaults come from the tool definition."""
    p = session.scalar(select(ToolPolicy).where(ToolPolicy.tool_key == key))  # RLS: this tenant's row only
    t = TOOLS[key]
    return (p.enabled, p.require_approval) if p else (True, t.sensitive_default)


def _say(e: WorkflowError) -> dict[str, Any]:
    return {"ok": False, "error": e.code, "message": e.message}


def _record(
    s: Session,
    *,
    actor: Actor,
    version_id: UUID | None,
    key: str,
    idem: str,
    status: str,
    args: dict[str, Any],
    result: dict[str, Any] | None,
    error: str | None,
    attempts: int = 1,
    latency_ms: int | None = None,
) -> ToolExecution:
    ex = ToolExecution(
        tenant_id=actor.tenant_id,
        call_id=actor.call_id,
        agent_version_id=version_id,
        tool_key=key,
        idempotency_key=idem,
        status=status,
        input=args,
        result=result,
        error=(error or None) and error[:300],
        attempts=attempts,
        latency_ms=latency_ms,
    )
    s.add(ex)
    s.flush()
    audit.record(
        s,
        action=f"tool.{status}",
        result={"succeeded": "success", "pending_approval": "allowed"}.get(
            status, "denied" if status == "rejected" else "failure"
        ),
        tenant_id=actor.tenant_id,
        actor_kind="service",
        resource_type="tool_execution",
        resource_id=str(ex.id),
        reason=error and error[:200],
        metadata={
            "tool": key,
            "call_id": str(actor.call_id) if actor.call_id else None,
            "agent_version_id": str(version_id) if version_id else None,
            "latency_ms": latency_ms,
        },
    )
    return ex


def _run_sync(
    t: ToolDef,
    actor: Actor,
    cfg: AgentConfig,
    version_id: UUID | None,
    idem: str,
    args: dict[str, Any],
    business_name: str,
    *,
    approved_execution: UUID | None = None,
) -> ToolOutcome:
    """Runs a validated tool in its own transaction (sync; called in a worker thread)."""
    timeout_ms = int(get_settings().tool_timeout_seconds * 1000)
    started = time.perf_counter()
    attempts = 0
    while True:
        attempts += 1
        try:
            with session_scope(tenant_id=actor.tenant_id) as s:
                s.execute(text("select set_config('statement_timeout', :v, true)"), {"v": str(timeout_ms)})
                parsed = t.schema.model_validate(args)
                ctx = ToolContext(actor=actor, cfg=cfg, business_name=business_name, idempotency_key=idem)
                try:
                    with s.begin_nested():
                        result = t.handler(s, ctx, parsed)
                    status, error = "succeeded", None
                except WorkflowError as e:
                    result, status, error = _say(e), "failed", e.message
                ms = int((time.perf_counter() - started) * 1000)
                if approved_execution:
                    ex = s.get(ToolExecution, approved_execution)
                    assert ex is not None
                    ex.status, ex.result, ex.error, ex.latency_ms = status, result, error, ms
                    ex.attempts = ex.attempts + attempts
                    audit.record(
                        s,
                        action=f"tool.{status}",
                        result="success" if status == "succeeded" else "failure",
                        tenant_id=actor.tenant_id,
                        actor_kind="service",
                        resource_type="tool_execution",
                        resource_id=str(ex.id),
                        metadata={"tool": t.key, "after_approval": True},
                    )
                else:
                    ex = _record(
                        s,
                        actor=actor,
                        version_id=version_id,
                        key=t.key,
                        idem=idem,
                        status=status,
                        args=args,
                        result=result,
                        error=error,
                        attempts=attempts,
                        latency_ms=ms,
                    )
                ok = {"ok": True} if status == "succeeded" else {}
                return ToolOutcome(status, ok | result, ex.id)
        except OperationalError:
            if attempts >= 2:
                raise
            time.sleep(0.2)


def _gate(
    s: Session, actor: Actor, cfg: AgentConfig, key: str, args: dict[str, Any]
) -> tuple[ToolDef | None, dict[str, Any] | None, str | None, bool]:
    """Authorization and validation. Returns (tool, clean args, refusal, needs approval)."""
    t = TOOLS.get(key)
    if t is None or key not in cfg.tools:
        return None, None, "This tool isn't permitted for this agent.", False
    enabled, approval = policy(s, key)
    if not enabled:
        return t, None, "This tool is turned off for your organization.", False
    why = unavailable(s, key, cfg)
    if why:
        return t, None, why, False
    try:
        clean = t.schema.model_validate(args).model_dump(mode="json")
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(x) for x in first.get("loc", ())) or "input"
        return t, None, f"Invalid input ({where}: {first.get('msg', 'invalid')}).", False
    return t, clean, None, approval


async def execute(
    *,
    actor: Actor,
    cfg: AgentConfig,
    version_id: UUID | None,
    key: str,
    args: dict[str, Any],
    idempotency_key: str,
    business_name: str,
) -> ToolOutcome:
    """Runs one tool call from a conversation. Never raises for a business outcome; the model is told what
    happened in plain terms so it can say it."""

    def prepare() -> ToolOutcome | tuple[ToolDef, dict[str, Any], bool]:
        with session_scope(tenant_id=actor.tenant_id) as s:
            prior = s.scalar(select(ToolExecution).where(ToolExecution.idempotency_key == idempotency_key))
            if prior:
                CALLS.labels(key, "replayed").inc()
                return ToolOutcome(prior.status, prior.result or {"status": prior.status}, prior.id)
            t, clean, refusal, approval = _gate(s, actor, cfg, key, args)
            if refusal or t is None or clean is None:
                safe_args = clean or {k: v for k, v in args.items() if isinstance(v, str | int | float | bool)}
                ex = _record(
                    s,
                    actor=actor,
                    version_id=version_id,
                    key=key if t else "unknown",
                    idem=idempotency_key,
                    status="rejected",
                    args=safe_args,
                    result=None,
                    error=refusal,
                )
                CALLS.labels(key if t else "unknown", "rejected").inc()
                return ToolOutcome("rejected", {"ok": False, "error": "not_allowed", "message": refusal}, ex.id)
            if approval:
                ex = _record(
                    s,
                    actor=actor,
                    version_id=version_id,
                    key=key,
                    idem=idempotency_key,
                    status="pending_approval",
                    args=clean,
                    result=None,
                    error=None,
                )
                CALLS.labels(key, "pending_approval").inc()
                return ToolOutcome(
                    "pending_approval",
                    {
                        "ok": False,
                        "pending_approval": True,
                        "message": "This needs a staff member's approval. Tell the caller the request is passed on "
                        "and they'll be contacted to confirm.",
                    },
                    ex.id,
                )
            return t, clean, approval

    gate = await run_in_threadpool(prepare)
    if isinstance(gate, ToolOutcome):
        return gate
    t, clean, _ = gate
    started = time.perf_counter()
    try:
        out = await asyncio.wait_for(
            run_in_threadpool(_run_sync, t, actor, cfg, version_id, idempotency_key, clean, business_name),
            timeout=get_settings().tool_timeout_seconds + 2,
        )
    except TimeoutError:
        CALLS.labels(key, "timeout").inc()
        return ToolOutcome("failed", {"ok": False, "error": "timeout", "message": "That took too long. Try again."})
    except Exception:  # noqa: BLE001 - the caller hears a plain failure; details go to the log, not the model
        log.exception("tool %s failed", key)
        CALLS.labels(key, "error").inc()
        return ToolOutcome("failed", {"ok": False, "error": "internal", "message": "Something went wrong."})
    LATENCY.labels(key).observe(time.perf_counter() - started)
    CALLS.labels(key, out.status).inc()
    return out


def decide(
    s: Session,
    ex: ToolExecution,
    *,
    approve: bool,
    membership_id: UUID,
    user_id: UUID,
    reason: str | None,
    cfg: AgentConfig | None,
    country: str,
    business_name: str,
) -> ToolExecution:
    """A person approves or denies a held action. Approving runs it now, with the input the caller gave."""
    ex.decided_by_membership_id, ex.decided_at = membership_id, datetime.now(UTC)
    ex.decision_reason = (reason or None) and reason[:300]
    if not approve:
        ex.status = "denied"
        return ex
    t = TOOLS[ex.tool_key]
    actor = Actor(
        tenant_id=ex.tenant_id, country=country, source="call", membership_id=membership_id, call_id=ex.call_id
    )
    ex.status = "approved"  # claimed: a second approver now gets a conflict, not a second run
    s.flush()
    s.commit()  # the decision is recorded even if running the action then fails
    s.begin()
    set_context(s, tenant_id=ex.tenant_id, user_id=user_id)
    out = _run_sync(
        t,
        actor,
        cfg or AgentConfig(),
        ex.agent_version_id,
        ex.idempotency_key,
        ex.input,
        business_name,
        approved_execution=ex.id,
    )
    CALLS.labels(ex.tool_key, f"approved_{out.status}").inc()
    s.refresh(ex)
    return ex


def specs(s: Session, cfg: AgentConfig) -> list[ToolSpec]:
    """The tools offered to the model on this turn: granted on the version, enabled for the tenant, and runnable
    now. A tool the model isn't offered can still be asked for by name; execute() refuses it."""
    out = []
    for key in cfg.tools:
        t = TOOLS.get(key)
        if t is None or not policy(s, key)[0] or unavailable(s, key, cfg):
            continue
        out.append(ToolSpec(name=t.key, description=t.description, parameters=json_schema(t)))
    return out


def actions_note(s: Session, call_id: UUID) -> str | None:
    """What tools already did on this call, from the record (not from the worker's history), so a barge-in or a
    worker restart never makes the agent forget a booking and make it twice."""
    rows = s.scalars(
        select(ToolExecution)
        .where(ToolExecution.call_id == call_id, ToolExecution.status.in_(("succeeded", "pending_approval")))
        .order_by(ToolExecution.created_at)
        .limit(10)
    ).all()
    if not rows:
        return None
    lines = [f"- {r.tool_key} ({r.status}): {json.dumps(r.result or r.input, default=str)[:400]}" for r in rows]
    return "Actions already taken on this call. Don't repeat them; refer to them if the caller asks:\n" + "\n".join(
        lines
    )
