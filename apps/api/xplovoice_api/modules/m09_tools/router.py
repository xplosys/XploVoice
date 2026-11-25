# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Business tools API: the tool catalog, the tenant's tool policies, every tool call agents made, and the approval
queue for sensitive actions."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from ...core.context import Ctx, require
from ...core.errors import conflict, not_found
from ...core.permissions import Perm
from ..m05_agents.models import AgentVersion
from ..m05_agents.schemas import AgentConfig
from . import gateway
from .models import ToolExecution, ToolPolicy
from .registry import TOOLS, json_schema

router = APIRouter(prefix="/v1/tools", tags=["tools"])


class ToolOut(BaseModel):
    key: str
    label: str
    description: str
    module: str
    enabled: bool
    require_approval: bool
    sensitive_default: bool
    input_schema: dict[str, Any]


class PolicyIn(BaseModel):
    enabled: bool
    require_approval: bool


class ExecutionOut(BaseModel):
    id: UUID
    tool_key: str
    label: str
    status: str
    call_id: UUID | None
    input: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    latency_ms: int | None
    attempts: int
    decided_at: datetime | None
    decision_reason: str | None
    created_at: datetime


class DecisionIn(BaseModel):
    decision: Literal["approve", "deny"]
    reason: str | None = Field(default=None, max_length=300)


def _tool_out(ctx: Ctx, key: str) -> ToolOut:
    t = TOOLS[key]
    enabled, approval = gateway.policy(ctx.session, key)
    return ToolOut(
        key=key,
        label=t.label,
        description=t.description,
        module=t.module,
        enabled=enabled,
        require_approval=approval,
        sensitive_default=t.sensitive_default,
        input_schema=json_schema(t),
    )


def _ex_out(e: ToolExecution) -> ExecutionOut:
    return ExecutionOut(
        id=e.id,
        tool_key=e.tool_key,
        label=TOOLS[e.tool_key].label if e.tool_key in TOOLS else e.tool_key,
        status=e.status,
        call_id=e.call_id,
        input=e.input or {},
        result=e.result,
        error=e.error,
        latency_ms=e.latency_ms,
        attempts=e.attempts,
        decided_at=e.decided_at,
        decision_reason=e.decision_reason,
        created_at=e.created_at,
    )


@router.get("", response_model=list[ToolOut])
def list_tools(ctx: Ctx = Depends(require(Perm.AGENTS_READ))) -> list[ToolOut]:
    return [_tool_out(ctx, k) for k in TOOLS]


@router.put("/{key}/policy", response_model=ToolOut)
def set_policy(key: str, data: PolicyIn, ctx: Ctx = Depends(require(Perm.TOOLS_MANAGE))) -> ToolOut:
    if key not in TOOLS:
        raise not_found()
    ctx.session.execute(
        insert(ToolPolicy)
        .values(
            tenant_id=ctx.tenant.id,
            tool_key=key,
            enabled=data.enabled,
            require_approval=data.require_approval,
            updated_by_membership_id=ctx.membership.id,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "tool_key"],
            set_={
                "enabled": data.enabled,
                "require_approval": data.require_approval,
                "updated_by_membership_id": ctx.membership.id,
            },
        )
    )
    ctx.audit(
        "tool.policy_changed",
        resource_type="tool",
        resource_id=key,
        enabled=data.enabled,
        require_approval=data.require_approval,
    )
    return _tool_out(ctx, key)


@router.get("/executions", response_model=list[ExecutionOut])
def list_executions(
    status_: str | None = Query(default=None, alias="status"),
    call_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    ctx: Ctx = Depends(require(Perm.CALLS_READ)),
) -> list[ExecutionOut]:
    q = select(ToolExecution)
    if status_:
        q = q.where(ToolExecution.status == status_)
    if call_id:
        q = q.where(ToolExecution.call_id == call_id)
    return [_ex_out(e) for e in ctx.session.scalars(q.order_by(ToolExecution.created_at.desc()).limit(limit))]


@router.post("/executions/{ex_id}/decision", response_model=ExecutionOut)
def decide(ex_id: UUID, data: DecisionIn, ctx: Ctx = Depends(require(Perm.TOOLS_APPROVE))) -> ExecutionOut:
    ex = ctx.session.scalar(
        select(ToolExecution)
        .where(ToolExecution.id == ex_id, ToolExecution.tenant_id == ctx.tenant.id)
        .with_for_update()
    )
    if not ex:
        raise not_found()
    if ex.status != "pending_approval":
        raise conflict("already_decided", "This request has already been decided.")
    cfg = None
    if ex.agent_version_id:
        v = ctx.session.get(AgentVersion, ex.agent_version_id)
        cfg = AgentConfig.model_validate(v.config) if v else None
    ctx.audit(
        f"tool.{'approved' if data.decision == 'approve' else 'denied'}",
        resource_type="tool_execution",
        resource_id=str(ex.id),
        tool=ex.tool_key,
        reason=data.reason,
    )
    ex = gateway.decide(
        ctx.session,
        ex,
        approve=data.decision == "approve",
        membership_id=ctx.membership.id,
        user_id=ctx.user.id,
        reason=data.reason,
        cfg=cfg,
        country=ctx.tenant.country_code,
        business_name=ctx.tenant.name,
    )
    return _ex_out(ex)
