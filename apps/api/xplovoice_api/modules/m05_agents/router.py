# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Minimal agents for the Phase 3 voice engine. Every save writes a new immutable version; calls pin the version
that was current when they started."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select

from ...core.context import Ctx, require
from ...core.errors import not_found
from ...core.permissions import Perm
from .models import Agent, AgentVersion
from .schemas import AgentConfig, AgentIn, AgentOut, VersionOut

router = APIRouter(prefix="/v1/agents", tags=["agents"])


def _out(a: Agent, v: AgentVersion) -> AgentOut:
    return AgentOut(
        id=a.id,
        name=a.name,
        status=a.status,
        version=v.version,
        version_id=v.id,
        config=AgentConfig.model_validate(v.config),
        updated_at=a.updated_at,
    )


def get_agent(ctx: Ctx, agent_id: UUID) -> tuple[Agent, AgentVersion]:
    a = ctx.session.scalar(select(Agent).where(Agent.id == agent_id, Agent.tenant_id == ctx.tenant.id))
    if not a or not a.current_version_id:
        raise not_found()
    v = ctx.session.get(AgentVersion, a.current_version_id)
    assert v is not None
    return a, v


def _new_version(ctx: Ctx, a: Agent, config: AgentConfig) -> AgentVersion:
    n = ctx.session.scalar(
        select(func.coalesce(func.max(AgentVersion.version), 0)).where(AgentVersion.agent_id == a.id)
    )
    v = AgentVersion(
        tenant_id=ctx.tenant.id,
        agent_id=a.id,
        version=(n or 0) + 1,
        config=config.model_dump(),
        created_by_membership_id=ctx.membership.id,
    )
    ctx.session.add(v)
    ctx.session.flush()
    a.current_version_id = v.id
    return v


@router.get("", response_model=list[AgentOut])
def list_agents(ctx: Ctx = Depends(require(Perm.AGENTS_READ))) -> list[AgentOut]:
    rows = ctx.session.execute(
        select(Agent, AgentVersion)
        .join(AgentVersion, AgentVersion.id == Agent.current_version_id)
        .where(Agent.tenant_id == ctx.tenant.id, Agent.status == "active")
        .order_by(Agent.created_at)
    ).all()
    return [_out(a, v) for a, v in rows]


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(data: AgentIn, ctx: Ctx = Depends(require(Perm.AGENTS_MANAGE))) -> AgentOut:
    a = Agent(tenant_id=ctx.tenant.id, name=data.name.strip(), created_by_membership_id=ctx.membership.id)
    ctx.session.add(a)
    ctx.session.flush()
    v = _new_version(ctx, a, data.config)
    ctx.audit("agent.created", resource_type="agent", resource_id=str(a.id), version=v.version)
    return _out(a, v)


@router.get("/{agent_id}", response_model=AgentOut)
def read_agent(agent_id: UUID, ctx: Ctx = Depends(require(Perm.AGENTS_READ))) -> AgentOut:
    return _out(*get_agent(ctx, agent_id))


@router.get("/{agent_id}/versions", response_model=list[VersionOut])
def versions(agent_id: UUID, ctx: Ctx = Depends(require(Perm.AGENTS_READ))) -> list[VersionOut]:
    get_agent(ctx, agent_id)
    rows = ctx.session.scalars(
        select(AgentVersion).where(AgentVersion.agent_id == agent_id).order_by(AgentVersion.version.desc())
    )
    return [VersionOut(id=v.id, version=v.version, created_at=v.created_at) for v in rows]


@router.put("/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: UUID, data: AgentIn, ctx: Ctx = Depends(require(Perm.AGENTS_MANAGE))) -> AgentOut:
    a, _ = get_agent(ctx, agent_id)
    a.name = data.name.strip()
    v = _new_version(ctx, a, data.config)
    ctx.audit("agent.updated", resource_type="agent", resource_id=str(a.id), version=v.version)
    return _out(a, v)


@router.post("/{agent_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
def archive_agent(agent_id: UUID, ctx: Ctx = Depends(require(Perm.AGENTS_MANAGE))) -> None:
    a, _ = get_agent(ctx, agent_id)
    a.status = "archived"
    ctx.audit("agent.archived", resource_type="agent", resource_id=str(a.id))
