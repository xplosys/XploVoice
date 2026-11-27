# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Agent builder (M05): agents, immutable versions, templates, readiness checks, and the lifecycle
draft -> testing -> published <-> paused -> archived (MP section 9; ADR 0007).

Two version pointers: `current_version_id` is the latest saved version, which test calls use; and
`published_version_id` is what live traffic reaches. Saving never changes what is live; publishing or rolling
back does, and only for calls that start afterwards. A running call keeps the version it started with."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.context import Ctx, require
from ...core.errors import ApiError, bad_request, conflict, not_found
from ...core.permissions import Perm, has
from ..m01_identity.models import User
from ..m02_tenant.models import Membership
from ..m15_usage import billing
from .checks import readiness
from .models import Agent, AgentPublication, AgentTemplate, AgentVersion
from .schemas import (
    AgentConfig,
    AgentCreate,
    AgentOut,
    AgentUpdate,
    PublicationOut,
    PublishIn,
    Readiness,
    RollbackIn,
    TemplateOut,
    VersionDetail,
    VersionOut,
)

router = APIRouter(tags=["agents"])
LIVE = ("published", "paused")
LATER_FIELDS = ("booking_calendar_id",)


# ---------------------------------------------------------------------------------------------------- helpers
def stored(name: str, cfg: AgentConfig) -> tuple[dict, str]:
    """The JSON kept on a version and its content hash. The agent's name is part of the version because the
    engine introduces itself by it."""
    body = cfg.model_dump(mode="json") | {"agent_name": name}
    # Fields added after Phase 4 are left out of the hash while unset, so upgrading doesn't make an unchanged
    # agent look changed.
    hashed = {k: v for k, v in body.items() if not (k in LATER_FIELDS and v is None)}
    digest = hashlib.sha256(json.dumps(hashed, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return body, digest


def get_agent(ctx: Ctx, agent_id: UUID) -> tuple[Agent, AgentVersion]:
    """The agent and its latest saved version."""
    a = ctx.session.scalar(select(Agent).where(Agent.id == agent_id, Agent.tenant_id == ctx.tenant.id))
    if not a or not a.current_version_id:
        raise not_found()
    v = ctx.session.get(AgentVersion, a.current_version_id)
    assert v is not None
    return a, v


def get_version(ctx: Ctx, a: Agent, version_id: UUID) -> AgentVersion:
    v = ctx.session.scalar(select(AgentVersion).where(AgentVersion.id == version_id, AgentVersion.agent_id == a.id))
    if not v:
        raise not_found("That version does not exist for this agent")
    return v


def production_version(session: Session, a: Agent) -> AgentVersion | None:
    """The version live traffic (inbound and outbound calls, Phase 6) must use: the published one, and only while
    the agent is published. Paused, draft, testing and archived agents take no live calls."""
    if a.status != "published" or not a.published_version_id:
        return None
    return session.get(AgentVersion, a.published_version_id)


def tested(session: Session, version_id: UUID) -> int:
    from ..m08_calls.models import Call  # calls depend on agents, not the other way round

    return (
        session.scalar(
            select(func.count())
            .select_from(Call)
            .where(
                Call.agent_version_id == version_id,
                Call.direction == "test",
                Call.status == "completed",
                Call.channel != "chat",  # a typed chat doesn't test speech, so it doesn't unlock publishing
            )
        )
        or 0
    )


def _ever_published(session: Session, a: Agent) -> set[UUID]:
    rows = session.scalars(
        select(AgentPublication.version_id).where(
            AgentPublication.agent_id == a.id, AgentPublication.action.in_(("publish", "rollback"))
        )
    )
    return {r for r in rows if r}


def _out(session: Session, a: Agent, v: AgentVersion) -> AgentOut:
    pub = session.get(AgentVersion, a.published_version_id) if a.published_version_id else None
    return AgentOut(
        id=a.id,
        name=a.name,
        description=a.description,
        status=a.status,
        template_key=a.template_key,
        version=v.version,
        version_id=v.id,
        config=AgentConfig.model_validate(v.config),
        published_version=pub.version if pub else None,
        published_version_id=pub.id if pub else None,
        published_at=a.published_at,
        has_unpublished_changes=pub is not None and pub.id != v.id,
        updated_at=a.updated_at,
    )


def _save_version(ctx: Ctx, a: Agent, cfg: AgentConfig, note: str | None) -> tuple[AgentVersion, bool]:
    """Writes a new immutable version unless nothing changed since the latest one."""
    body, digest = stored(a.name, cfg)
    if a.current_version_id:
        cur = ctx.session.get(AgentVersion, a.current_version_id)
        if cur and cur.content_hash == digest:
            return cur, False
    n = ctx.session.scalar(
        select(func.coalesce(func.max(AgentVersion.version), 0)).where(AgentVersion.agent_id == a.id)
    )
    v = AgentVersion(
        tenant_id=ctx.tenant.id,
        agent_id=a.id,
        version=(n or 0) + 1,
        config=body,
        content_hash=digest,
        note=(note or "").strip() or None,
        created_by_membership_id=ctx.membership.id,
    )
    ctx.session.add(v)
    ctx.session.flush()
    a.current_version_id = v.id
    return v, True


def _record(ctx: Ctx, a: Agent, action: str, version: AgentVersion | None, reason: str | None = None) -> None:
    ctx.session.add(
        AgentPublication(
            tenant_id=ctx.tenant.id,
            agent_id=a.id,
            version_id=version.id if version else None,
            action=action,
            reason=reason,
            created_by_membership_id=ctx.membership.id,
        )
    )
    ctx.audit(
        f"agent.{action}",
        resource_type="agent",
        resource_id=str(a.id),
        reason=reason,
        version=version.version if version else None,
    )


def _not_archived(a: Agent) -> None:
    if a.status == "archived":
        raise conflict("agent_archived", "This agent is archived. Restore it first.")


# ---------------------------------------------------------------------------------------------------- templates
@router.get("/v1/agent-templates", response_model=list[TemplateOut])
def list_templates(ctx: Ctx = Depends(require(Perm.AGENTS_READ))) -> list[TemplateOut]:
    rows = ctx.session.scalars(
        select(AgentTemplate).where(AgentTemplate.status == "active").order_by(AgentTemplate.sort)
    )
    return [
        TemplateOut(key=t.key, name=t.name, category=t.category, description=t.description, config=t.config)
        for t in rows
    ]


# ---------------------------------------------------------------------------------------------------- agents
@router.get("/v1/agents", response_model=list[AgentOut])
def list_agents(
    include_archived: bool = Query(default=False), ctx: Ctx = Depends(require(Perm.AGENTS_READ))
) -> list[AgentOut]:
    q = (
        select(Agent, AgentVersion)
        .join(AgentVersion, AgentVersion.id == Agent.current_version_id)
        .where(Agent.tenant_id == ctx.tenant.id)
        .order_by(Agent.created_at)
    )
    if not include_archived:
        q = q.where(Agent.status != "archived")
    return [_out(ctx.session, a, v) for a, v in ctx.session.execute(q).all()]


@router.post("/v1/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(data: AgentCreate, ctx: Ctx = Depends(require(Perm.AGENTS_MANAGE))) -> AgentOut:
    cfg = data.config or AgentConfig()
    if data.template_key:
        t = ctx.session.get(AgentTemplate, data.template_key)
        if not t or t.status != "active":
            raise bad_request("unknown_template", "That template does not exist")
        cfg = data.config or AgentConfig.model_validate(t.config)
    limit = billing.plan_limit(ctx.session, "max_agents")
    if limit is not None:
        n = ctx.session.scalar(
            select(func.count()).select_from(Agent).where(Agent.tenant_id == ctx.tenant.id, Agent.status != "archived")
        )
        if (n or 0) >= limit:
            raise ApiError(402, "plan_limit", f"Your plan allows {limit} agents. Archive one or change plan.")
    a = Agent(
        tenant_id=ctx.tenant.id,
        name=data.name.strip(),
        description=data.description.strip(),
        template_key=data.template_key,
        status="draft",
        created_by_membership_id=ctx.membership.id,
    )
    ctx.session.add(a)
    ctx.session.flush()
    note = f"Created from the {data.template_key} template" if data.template_key else "Created"
    v, _ = _save_version(ctx, a, cfg, note)
    ctx.audit(
        "agent.created", resource_type="agent", resource_id=str(a.id), version=v.version, template=data.template_key
    )
    return _out(ctx.session, a, v)


@router.get("/v1/agents/{agent_id}", response_model=AgentOut)
def read_agent(agent_id: UUID, ctx: Ctx = Depends(require(Perm.AGENTS_READ))) -> AgentOut:
    return _out(ctx.session, *get_agent(ctx, agent_id))


@router.put("/v1/agents/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: UUID, data: AgentUpdate, ctx: Ctx = Depends(require(Perm.AGENTS_MANAGE))) -> AgentOut:
    a, _ = get_agent(ctx, agent_id)
    _not_archived(a)
    a.name, a.description = data.name.strip(), data.description.strip()
    v, created = _save_version(ctx, a, data.config, data.note)
    if created:
        ctx.audit("agent.updated", resource_type="agent", resource_id=str(a.id), version=v.version)
    return _out(ctx.session, a, v)


@router.get("/v1/agents/{agent_id}/versions", response_model=list[VersionOut])
def versions(agent_id: UUID, ctx: Ctx = Depends(require(Perm.AGENTS_READ))) -> list[VersionOut]:
    a, _ = get_agent(ctx, agent_id)
    return [_version_out(ctx.session, a, v, by, set_) for v, by, set_ in _versions(ctx.session, a)]


def _versions(session: Session, a: Agent):  # type: ignore[no-untyped-def]
    ever = _ever_published(session, a)
    rows = session.execute(
        select(AgentVersion, User.display_name)
        .outerjoin(Membership, Membership.id == AgentVersion.created_by_membership_id)
        .outerjoin(User, User.id == Membership.user_id)
        .where(AgentVersion.agent_id == a.id)
        .order_by(AgentVersion.version.desc())
    ).all()
    return [(v, by, ever) for v, by in rows]


def _version_out(session: Session, a: Agent, v: AgentVersion, by: str | None, ever: set[UUID]) -> VersionOut:
    return VersionOut(
        id=v.id,
        version=v.version,
        created_at=v.created_at,
        created_by=by,
        note=v.note,
        content_hash=v.content_hash,
        is_published=v.id == a.published_version_id,
        was_published=v.id in ever,
        test_calls=tested(session, v.id),
    )


@router.get("/v1/agents/{agent_id}/versions/{number}", response_model=VersionDetail)
def version_detail(agent_id: UUID, number: int, ctx: Ctx = Depends(require(Perm.AGENTS_READ))) -> VersionDetail:
    a, _ = get_agent(ctx, agent_id)
    for v, by, ever in _versions(ctx.session, a):
        if v.version == number:
            base = _version_out(ctx.session, a, v, by, ever)
            return VersionDetail(**base.model_dump(), config=AgentConfig.model_validate(v.config))
    raise not_found("That version does not exist for this agent")


@router.get("/v1/agents/{agent_id}/readiness", response_model=Readiness)
def agent_readiness(
    agent_id: UUID, version_id: UUID | None = Query(default=None), ctx: Ctx = Depends(require(Perm.AGENTS_READ))
) -> Readiness:
    a, v = get_agent(ctx, agent_id)
    if version_id:
        v = get_version(ctx, a, version_id)
    checks = readiness(ctx.session, AgentConfig.model_validate(v.config))
    return Readiness(
        version=v.version,
        ready=not any(c.level == "error" for c in checks),
        tested=tested(ctx.session, v.id) > 0,
        checks=checks,
    )


@router.get("/v1/agents/{agent_id}/history", response_model=list[PublicationOut])
def history(agent_id: UUID, ctx: Ctx = Depends(require(Perm.AGENTS_READ))) -> list[PublicationOut]:
    a, _ = get_agent(ctx, agent_id)
    rows = ctx.session.execute(
        select(AgentPublication, AgentVersion.version, User.display_name)
        .outerjoin(AgentVersion, AgentVersion.id == AgentPublication.version_id)
        .outerjoin(Membership, Membership.id == AgentPublication.created_by_membership_id)
        .outerjoin(User, User.id == Membership.user_id)
        .where(AgentPublication.agent_id == a.id)
        .order_by(AgentPublication.id.desc())
        .limit(200)
    ).all()
    return [
        PublicationOut(action=p.action, version=n, reason=p.reason, actor=by, created_at=p.created_at)
        for p, n, by in rows
    ]


# ---------------------------------------------------------------------------------------------------- lifecycle
@router.post("/v1/agents/{agent_id}/publish", response_model=AgentOut)
def publish(agent_id: UUID, data: PublishIn, ctx: Ctx = Depends(require(Perm.AGENTS_PUBLISH))) -> AgentOut:
    """Makes a version live for calls that start from now on. A version must pass its readiness checks and have
    at least one completed test call, unless an owner or admin records why they are skipping the test."""
    a, latest = get_agent(ctx, agent_id)
    _not_archived(a)
    v = get_version(ctx, a, data.version_id) if data.version_id else latest
    if v.id == a.published_version_id:
        raise conflict("already_published", f"Version {v.version} is already published")
    checks = readiness(ctx.session, AgentConfig.model_validate(v.config))
    errors = [c for c in checks if c.level == "error"]
    if errors:
        err = ApiError(422, "not_ready", f"Version {v.version} is not ready to publish: {errors[0].message}")
        err.detail["checks"] = [c.model_dump() for c in errors]
        raise err
    if not tested(ctx.session, v.id) and v.id not in _ever_published(ctx.session, a):
        if not data.skip_test_reason:
            raise conflict(
                "not_tested",
                f"Make a test call on version {v.version} before publishing it, or give a reason for skipping it.",
            )
        if not has(ctx.membership.role, Perm.TENANT_MANAGE):
            raise ApiError(403, "forbidden", "Only an owner or admin can publish without a test call")
    reason = f"Published without a test call: {data.skip_test_reason}" if data.skip_test_reason else None
    a.published_version_id, a.published_at = v.id, datetime.now(UTC)
    a.status = "published"
    _record(ctx, a, "publish", v, reason)
    return _out(ctx.session, a, latest)


@router.post("/v1/agents/{agent_id}/rollback", response_model=AgentOut)
def rollback(agent_id: UUID, data: RollbackIn, ctx: Ctx = Depends(require(Perm.AGENTS_PUBLISH))) -> AgentOut:
    """Makes a previously published version live again (HLD v1.0: "activating a previous version"). Running
    calls keep the version they started with. A paused agent stays paused."""
    a, latest = get_agent(ctx, agent_id)
    _not_archived(a)
    if a.status not in LIVE:
        raise conflict("not_published", "Only a published or paused agent can be rolled back")
    v = get_version(ctx, a, data.version_id)
    if v.id == a.published_version_id:
        raise conflict("already_published", f"Version {v.version} is already the published version")
    if v.id not in _ever_published(ctx.session, a):
        raise conflict(
            "never_published", f"Version {v.version} was never published. Publish it instead of rolling back."
        )
    a.published_version_id, a.published_at = v.id, datetime.now(UTC)
    _record(ctx, a, "rollback", v, data.reason)
    return _out(ctx.session, a, latest)


@router.post("/v1/agents/{agent_id}/pause", response_model=AgentOut)
def pause(agent_id: UUID, ctx: Ctx = Depends(require(Perm.AGENTS_PUBLISH))) -> AgentOut:
    a, latest = get_agent(ctx, agent_id)
    if a.status != "published":
        raise conflict("not_published", "Only a published agent can be paused")
    a.status = "paused"
    _record(ctx, a, "pause", ctx.session.get(AgentVersion, a.published_version_id))
    return _out(ctx.session, a, latest)


@router.post("/v1/agents/{agent_id}/resume", response_model=AgentOut)
def resume(agent_id: UUID, ctx: Ctx = Depends(require(Perm.AGENTS_PUBLISH))) -> AgentOut:
    a, latest = get_agent(ctx, agent_id)
    if a.status != "paused":
        raise conflict("not_paused", "Only a paused agent can be resumed")
    a.status = "published"
    _record(ctx, a, "resume", ctx.session.get(AgentVersion, a.published_version_id))
    return _out(ctx.session, a, latest)


@router.post("/v1/agents/{agent_id}/archive", response_model=AgentOut)
def archive(agent_id: UUID, ctx: Ctx = Depends(require(Perm.AGENTS_MANAGE))) -> AgentOut:
    """Stops all new calls. Archiving a live agent needs publish rights, because it takes it off the air."""
    a, latest = get_agent(ctx, agent_id)
    _not_archived(a)
    if a.status in LIVE:
        ctx.require(Perm.AGENTS_PUBLISH)
    a.status = "archived"
    _record(ctx, a, "archive", None)
    return _out(ctx.session, a, latest)


@router.post("/v1/agents/{agent_id}/restore", response_model=AgentOut)
def restore(agent_id: UUID, ctx: Ctx = Depends(require(Perm.AGENTS_MANAGE))) -> AgentOut:
    """Brings an archived agent back. One that had a published version comes back paused, never straight to
    live traffic; others come back as a draft (or testing, once tested)."""
    a, latest = get_agent(ctx, agent_id)
    if a.status != "archived":
        raise conflict("not_archived", "Only an archived agent can be restored")
    if a.published_version_id:
        a.status = "paused"
    else:
        from ..m08_calls.models import Call

        any_test = ctx.session.scalar(select(func.count()).select_from(Call).where(Call.agent_id == a.id))
        a.status = "testing" if any_test else "draft"
    _record(ctx, a, "restore", None)
    return _out(ctx.session, a, latest)
