# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Super Admin (platform) API. Separate privileged path (HLD v1.0 section 6): requires the platform-admin flag,
an MFA-verified session and a written reason for every change. Every call is audited on the platform chain."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from ...core import audit
from ...core.context import Ctx, enable_platform_admin, get_ctx
from ...core.errors import forbidden, not_found
from ..m02_tenant.models import Membership, Tenant

router = APIRouter(prefix="/admin/v1", tags=["M17 Super Admin"])


def platform_admin(ctx: Ctx = Depends(get_ctx)) -> Ctx:
    if not ctx.user.is_platform_admin:
        ctx.audit("admin.access", result="denied")
        ctx.session.commit()
        raise forbidden()
    if not ctx.mfa:
        raise forbidden("Platform administration requires a session signed in with MFA")
    enable_platform_admin(ctx.session)
    return ctx


class AdminTenantOut(BaseModel):
    id: UUID
    name: str
    slug: str
    country_code: str
    currency: str
    status: str
    members: int
    created_at: datetime


class ReasonIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


def _log(ctx: Ctx, action: str, tenant_id: UUID | None, reason: str | None = None) -> None:
    audit.record(
        ctx.session,
        action=action,
        result="success",
        tenant_id=None,
        actor_user_id=ctx.user.id,
        actor_kind="platform_admin",
        resource_type="tenant",
        resource_id=str(tenant_id) if tenant_id else None,
        reason=reason,
        ip_hash=ctx.meta.ip_hash,
        correlation_id=ctx.meta.correlation_id,
    )


@router.get("/tenants", response_model=list[AdminTenantOut])
def list_tenants(
    ctx: Ctx = Depends(platform_admin), q: str | None = Query(None, max_length=80), limit: int = Query(50, ge=1, le=200)
) -> list[AdminTenantOut]:
    members = (
        select(Membership.tenant_id, func.count().label("n"))
        .where(Membership.status == "active")
        .group_by(Membership.tenant_id)
        .subquery()
    )
    stmt = select(Tenant, func.coalesce(members.c.n, 0)).outerjoin(members, members.c.tenant_id == Tenant.id)
    if q:
        stmt = stmt.where(Tenant.name.ilike(f"%{q}%"))
    rows = ctx.session.execute(stmt.order_by(Tenant.created_at.desc()).limit(limit)).all()
    _log(ctx, "admin.tenants_listed", None)
    return [
        AdminTenantOut(
            id=t.id,
            name=t.name,
            slug=t.slug,
            country_code=t.country_code,
            currency=t.currency,
            status=t.status,
            members=n,
            created_at=t.created_at,
        )
        for t, n in rows
    ]


def _set_status(ctx: Ctx, tenant_id: UUID, status: str, reason: str) -> AdminTenantOut:
    t = ctx.session.get(Tenant, tenant_id)
    if not t:
        raise not_found("Tenant not found")
    if t.id == ctx.tenant.id and status == "suspended":
        raise forbidden("You cannot suspend your own organization")
    t.status = status
    t.suspended_reason = reason if status == "suspended" else None
    _log(ctx, f"admin.tenant_{status}", t.id, reason)
    if status == "suspended":  # end all sessions in that tenant
        ctx.session.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(t.id)})
        ctx.session.execute(text("update refresh_tokens set revoked_at = now() where revoked_at is null"))
        ctx.session.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(ctx.tenant.id)})
    n = (
        ctx.session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.tenant_id == t.id, Membership.status == "active")
        )
        or 0
    )
    return AdminTenantOut(
        id=t.id,
        name=t.name,
        slug=t.slug,
        country_code=t.country_code,
        currency=t.currency,
        status=t.status,
        members=n,
        created_at=t.created_at,
    )


@router.post("/tenants/{tenant_id}/suspend", response_model=AdminTenantOut)
def suspend(tenant_id: UUID, data: ReasonIn, ctx: Ctx = Depends(platform_admin)) -> AdminTenantOut:
    return _set_status(ctx, tenant_id, "suspended", data.reason)


@router.post("/tenants/{tenant_id}/reactivate", response_model=AdminTenantOut)
def reactivate(tenant_id: UUID, data: ReasonIn, ctx: Ctx = Depends(platform_admin)) -> AdminTenantOut:
    return _set_status(ctx, tenant_id, "active", data.reason)
