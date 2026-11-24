# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import column, func, select, table, text
from sqlalchemy.orm import Session

from ...core import audit
from ...core.config import get_settings
from ...core.context import Ctx, get_ctx, request_meta, require
from ...core.db import set_context
from ...core.errors import bad_request, conflict, forbidden, not_found, unauthorized
from ...core.permissions import ROLE_RANK, Perm
from ...core.public import get_public_session
from ...core.security import hash_password, new_token, token_hash
from ..m01_identity import service as identity
from ..m01_identity.models import User
from ..m01_identity.schemas import TokenOut, _strong
from .models import Invitation, Membership, Tenant
from .regional import COUNTRIES, is_valid_timezone
from .schemas import (
    AcceptInviteIn,
    AuditOut,
    CountryOut,
    InvitationOut,
    InviteIn,
    InviteOut,
    LanguageOut,
    MemberOut,
    MemberPatch,
    MyTenantOut,
    TenantOut,
    TenantPatch,
)

router = APIRouter(tags=["M02 Tenant Management"])
INVITE_DAYS = 7


def _tenant_out(t: Tenant) -> TenantOut:
    return TenantOut.model_validate(t, from_attributes=True)


@router.get("/v1/reference/countries", response_model=list[CountryOut])
def countries() -> list[CountryOut]:
    return [
        CountryOut(
            code=c.code,
            name=c.name,
            currency=c.currency,
            default_timezone=c.default_timezone,
            timezones=list(c.timezones),
            date_format=c.date_format,
            languages=[LanguageOut(code=lang.code, name=lang.name) for lang in c.languages],
        )
        for c in COUNTRIES.values()
    ]


@router.get("/v1/tenants/current", response_model=TenantOut)
def current_tenant(ctx: Ctx = Depends(require(Perm.TENANT_READ))) -> TenantOut:
    return _tenant_out(ctx.tenant)


@router.patch("/v1/tenants/current", response_model=TenantOut)
def update_tenant(data: TenantPatch, ctx: Ctx = Depends(require(Perm.TENANT_MANAGE))) -> TenantOut:
    changes = data.model_dump(exclude_unset=True)
    if "timezone" in changes and not is_valid_timezone(changes["timezone"]):
        raise bad_request("invalid_timezone", "Unknown IANA time zone")
    if "default_language" in changes:
        allowed = {lang.code for lang in COUNTRIES[ctx.tenant.country_code].languages}
        if changes["default_language"] not in allowed:
            raise bad_request("invalid_language", f"Choose one of: {', '.join(sorted(allowed))}")
    if "website" in changes and changes["website"] is not None:
        changes["website"] = str(changes["website"])
    for k, v in changes.items():
        setattr(ctx.tenant, k, v)
    ctx.audit("tenant.updated", resource_type="tenant", resource_id=str(ctx.tenant.id), fields=sorted(changes))
    ctx.session.flush()
    ctx.session.refresh(ctx.tenant)
    return _tenant_out(ctx.tenant)


@router.get("/v1/tenants/mine", response_model=list[MyTenantOut])
def my_tenants(ctx: Ctx = Depends(get_ctx)) -> list[MyTenantOut]:
    set_context(ctx.session, user_id=ctx.user.id)
    rows = ctx.session.execute(
        select(Membership.tenant_id, Membership.role, Tenant.name)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == ctx.user.id, Membership.status == "active", Tenant.status == "active")
        .order_by(Tenant.name)
    ).all()
    set_context(ctx.session, tenant_id=ctx.tenant.id, user_id=ctx.user.id)
    return [
        MyTenantOut(tenant_id=r.tenant_id, name=r.name, role=r.role, current=r.tenant_id == ctx.tenant.id) for r in rows
    ]


# ------------------------------------------------------------------ members
@router.get("/v1/members", response_model=list[MemberOut])
def list_members(ctx: Ctx = Depends(require(Perm.MEMBERS_READ))) -> list[MemberOut]:
    rows = ctx.session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == ctx.tenant.id, Membership.status == "active")
        .order_by(Membership.created_at)
    ).all()
    return [
        MemberOut(
            id=m.id,
            user_id=u.id,
            email=u.email,
            display_name=u.display_name,
            role=m.role,
            mfa_enabled=u.mfa_enabled,
            created_at=m.created_at,
        )
        for m, u in rows
    ]


def _get_member(ctx: Ctx, member_id: UUID) -> Membership:
    m = ctx.session.scalar(
        select(Membership).where(
            Membership.tenant_id == ctx.tenant.id, Membership.id == member_id, Membership.status == "active"
        )
    )
    if not m:  # RLS hides other tenants' rows, so cross-tenant ids are indistinguishable from missing ones
        raise not_found("Member not found")
    return m


def _owners(ctx: Ctx) -> int:
    return (
        ctx.session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.tenant_id == ctx.tenant.id, Membership.role == "owner", Membership.status == "active")
        )
        or 0
    )


def _guard_rank(ctx: Ctx, target_role: str) -> None:
    # Nobody can grant or manage a role above their own; only owners manage owners.
    if ROLE_RANK[target_role] > ROLE_RANK[ctx.membership.role]:
        raise forbidden("You cannot manage a role higher than your own")


@router.patch("/v1/members/{member_id}", response_model=MemberOut)
def update_member(member_id: UUID, data: MemberPatch, ctx: Ctx = Depends(require(Perm.MEMBERS_MANAGE))) -> MemberOut:
    m = _get_member(ctx, member_id)
    _guard_rank(ctx, m.role)
    _guard_rank(ctx, data.role)
    if m.role == "owner" and data.role != "owner" and _owners(ctx) <= 1:
        raise conflict("last_owner", "An organization needs at least one owner")
    old = m.role
    m.role = data.role
    if old != data.role:
        identity.revoke_all_for_user_in_tenant(ctx.session, m.user_id)
    ctx.audit("member.role_changed", resource_type="membership", resource_id=str(m.id), old=old, new=data.role)
    u = ctx.session.get(User, m.user_id)
    assert u is not None
    return MemberOut(
        id=m.id,
        user_id=u.id,
        email=u.email,
        display_name=u.display_name,
        role=m.role,
        mfa_enabled=u.mfa_enabled,
        created_at=m.created_at,
    )


@router.delete("/v1/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(member_id: UUID, ctx: Ctx = Depends(require(Perm.MEMBERS_MANAGE))) -> None:
    m = _get_member(ctx, member_id)
    _guard_rank(ctx, m.role)
    if m.role == "owner" and _owners(ctx) <= 1:
        raise conflict("last_owner", "An organization needs at least one owner")
    m.status = "removed"
    identity.revoke_all_for_user_in_tenant(ctx.session, m.user_id)
    ctx.audit("member.removed", resource_type="membership", resource_id=str(m.id))


# ------------------------------------------------------------------ invitations
@router.get("/v1/invitations", response_model=list[InvitationOut])
def list_invitations(ctx: Ctx = Depends(require(Perm.MEMBERS_READ))) -> list[InvitationOut]:
    rows = ctx.session.scalars(select(Invitation).order_by(Invitation.created_at.desc()).limit(200)).all()
    return [InvitationOut.model_validate(i, from_attributes=True) for i in rows]


@router.post("/v1/invitations", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def invite(data: InviteIn, ctx: Ctx = Depends(require(Perm.MEMBERS_MANAGE))) -> InviteOut:
    _guard_rank(ctx, data.role)
    existing = ctx.session.scalar(
        select(Membership.id)
        .join(User, User.id == Membership.user_id)
        .where(User.email == data.email, Membership.tenant_id == ctx.tenant.id, Membership.status == "active")
    )
    if existing:
        raise conflict("already_member", "This person is already a member")
    raw = new_token()
    inv = Invitation(
        tenant_id=ctx.tenant.id,
        email=data.email,
        role=data.role,
        token_hash=token_hash(raw),
        invited_by_membership_id=ctx.membership.id,
        expires_at=datetime.now(UTC) + timedelta(days=INVITE_DAYS),
    )
    ctx.session.add(inv)
    ctx.session.flush()
    ctx.audit("member.invited", resource_type="invitation", resource_id=str(inv.id), role=data.role)
    # Email delivery is awaiting configuration (no provider yet). Outside production the link is returned so
    # an admin can share it; in production the API never returns the token.
    url = None if get_settings().is_production_like else f"/invite/accept?token={raw}"
    return InviteOut(id=inv.id, email=inv.email, role=inv.role, expires_at=inv.expires_at, accept_url=url)


@router.delete("/v1/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(invitation_id: UUID, ctx: Ctx = Depends(require(Perm.MEMBERS_MANAGE))) -> None:
    inv = ctx.session.get(Invitation, invitation_id)
    if not inv or inv.accepted_at or inv.revoked_at:
        raise not_found("Invitation not found")
    inv.revoked_at = datetime.now(UTC)
    ctx.audit("member.invitation_revoked", resource_type="invitation", resource_id=str(inv.id))


def _load_invite(session: Session, raw: str) -> Invitation:
    h = token_hash(raw)
    tid = session.execute(text("select tenant_id from lookup_invitation(:h)"), {"h": h}).scalar()
    if not tid:
        raise not_found("This invitation is invalid or has expired")
    set_context(session, tenant_id=tid)
    inv = session.scalar(select(Invitation).where(Invitation.token_hash == h).with_for_update())
    if not inv:
        raise not_found("This invitation is invalid or has expired")
    return inv


def _join(session: Session, inv: Invitation, user: User, meta_ip: str | None, cid: str | None) -> Membership:
    set_context(session, tenant_id=inv.tenant_id, user_id=user.id)
    m = session.scalar(select(Membership).where(Membership.tenant_id == inv.tenant_id, Membership.user_id == user.id))
    if m and m.status == "active":
        raise conflict("already_member", "You are already a member of this organization")
    if m:
        m.status, m.role = "active", inv.role
    else:
        m = Membership(tenant_id=inv.tenant_id, user_id=user.id, role=inv.role)
        session.add(m)
    inv.accepted_at = datetime.now(UTC)
    session.flush()
    audit.record(
        session,
        action="member.joined",
        result="success",
        tenant_id=inv.tenant_id,
        actor_user_id=user.id,
        resource_type="membership",
        resource_id=str(m.id),
        ip_hash=meta_ip,
        correlation_id=cid,
        metadata={"role": inv.role},
    )
    return m


@router.post("/v1/invitations/accept", response_model=TokenOut)
def accept_invite(data: AcceptInviteIn, ctx: Ctx = Depends(get_ctx)) -> TokenOut:
    """Accept as an existing signed-in user. The invitation email must match the account email."""
    inv = _load_invite(ctx.session, data.token)
    if inv.email.lower() != ctx.user.email.lower():
        raise forbidden("This invitation was sent to a different email address")
    m = _join(ctx.session, inv, ctx.user, ctx.meta.ip_hash, ctx.meta.correlation_id)
    return identity.issue_session(ctx.session, user=ctx.user, membership=m, mfa=ctx.mfa)


class AcceptNewIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(max_length=256)

    _pw = field_validator("password")(_strong)


@router.post("/v1/invitations/accept-new", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def accept_invite_new(data: AcceptNewIn, request: Request, session: Session = Depends(get_public_session)) -> TokenOut:
    """Create an account from an invitation. The email is taken from the invitation, not the request."""
    meta = request_meta(request)
    inv = _load_invite(session, data.token)
    if session.scalar(select(User.id).where(User.email == inv.email)):
        raise unauthorized("account_exists", "An account with this email exists. Sign in to accept.")
    user = User(
        email=inv.email,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
        email_verified_at=func.now(),
    )  # possession of the emailed token verifies the address
    session.add(user)
    session.flush()
    m = _join(session, inv, user, meta.ip_hash, meta.correlation_id)
    return identity.issue_session(session, user=user, membership=m, mfa=False)


# ------------------------------------------------------------------ audit (tenant scope)
_AUDIT = table(
    "audit_log",
    *(
        column(c)
        for c in (
            "id",
            "tenant_id",
            "created_at",
            "actor_user_id",
            "actor_kind",
            "action",
            "resource_type",
            "resource_id",
            "result",
            "correlation_id",
        )
    ),
)


@router.get("/v1/audit-logs", response_model=list[AuditOut])
def audit_logs(
    ctx: Ctx = Depends(require(Perm.AUDIT_READ)), limit: int = Query(50, ge=1, le=200), before_id: int | None = None
) -> list[AuditOut]:
    a = _AUDIT
    stmt = select(
        a.c.id,
        a.c.created_at,
        a.c.actor_user_id,
        a.c.actor_kind,
        a.c.action,
        a.c.resource_type,
        a.c.resource_id,
        a.c.result,
        a.c.correlation_id,
    ).where(a.c.tenant_id == func.app_tenant_id())
    if before_id:
        stmt = stmt.where(a.c.id < before_id)
    rows = ctx.session.execute(stmt.order_by(a.c.id.desc()).limit(limit)).mappings().all()
    return [AuditOut(**r) for r in rows]
