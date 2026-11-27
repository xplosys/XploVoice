# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Identity service: registration, login with lockout and MFA, refresh-token rotation with reuse detection."""

import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pyotp
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from ...core import audit
from ...core.config import get_settings
from ...core.context import RequestMeta
from ...core.db import set_context
from ...core.errors import bad_request, conflict, unauthorized
from ...core.security import (
    decrypt_secret,
    hash_password,
    issue_access_token,
    new_token,
    token_hash,
    verify_password,
)
from ..m02_tenant.models import Membership, Tenant
from ..m02_tenant.regional import COUNTRIES, is_valid_timezone
from .models import RefreshToken, User
from .schemas import LoginIn, RegisterIn, TokenOut

MAX_FAILED = 5
LOCK_MINUTES = 15


def _now() -> datetime:
    return datetime.now(UTC)


def _slugify(name: str, session: Session) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "org"
    if len(base) < 2:
        base = f"{base}-org"
    slug = base
    while not session.execute(text("select slug_available(:s)"), {"s": slug}).scalar():
        slug = f"{base}-{secrets.token_hex(3)}"
    return slug


def issue_session(
    session: Session, *, user: User, membership: Membership, mfa: bool, family_id: UUID | None = None
) -> TokenOut:
    set_context(session, tenant_id=membership.tenant_id, user_id=user.id)
    raw = new_token()
    family = family_id or uuid4()
    rt = RefreshToken(
        tenant_id=membership.tenant_id,
        user_id=user.id,
        membership_id=membership.id,
        family_id=family,
        token_hash=token_hash(raw),
        mfa=mfa,
        expires_at=_now() + timedelta(days=get_settings().refresh_token_days),
    )
    session.add(rt)
    session.flush()
    access, exp = issue_access_token(
        user_id=user.id, tenant_id=membership.tenant_id, membership_id=membership.id, session_id=family, mfa=mfa
    )
    return TokenOut(access_token=access, access_expires_at=exp, refresh_token=raw, tenant_id=membership.tenant_id)


def register(session: Session, data: RegisterIn, meta: RequestMeta) -> TokenOut:
    profile = COUNTRIES[data.country_code]
    tz = data.timezone or profile.default_timezone
    if not is_valid_timezone(tz):
        raise bad_request("invalid_timezone", "Unknown IANA time zone")
    if session.scalar(select(User.id).where(User.email == data.email)):
        # Same message shape as success would leak nothing more than a conflict; registration is public anyway.
        raise conflict("email_taken", "An account with this email already exists. Sign in instead.")

    user = User(email=data.email, password_hash=hash_password(data.password), display_name=data.display_name)
    session.add(user)
    session.flush()

    tenant_id = uuid4()
    set_context(session, tenant_id=tenant_id, user_id=user.id)
    tenant = Tenant(
        id=tenant_id,
        name=data.organization_name,
        slug=_slugify(data.organization_name, session),
        country_code=profile.code,
        timezone=tz,
        currency=profile.currency,
        default_language=profile.languages[0].code,
        date_format=profile.date_format,
    )
    session.add(tenant)
    session.flush()
    membership = Membership(tenant_id=tenant_id, user_id=user.id, role="owner")
    session.add(membership)
    session.flush()
    audit.record(
        session,
        action="tenant.created",
        result="success",
        tenant_id=tenant_id,
        actor_user_id=user.id,
        resource_type="tenant",
        resource_id=str(tenant_id),
        ip_hash=meta.ip_hash,
        correlation_id=meta.correlation_id,
        metadata={"country": profile.code},
    )
    from ..m15_usage import billing  # a new organisation starts on the platform's default plan, when one is set

    plan = billing.default_plan_for(session, profile.currency)
    if plan is not None:
        billing.subscribe(session, plan, source="default_plan", membership_id=membership.id)
        audit.record(
            session,
            action="subscription.started",
            result="success",
            tenant_id=tenant_id,
            actor_kind="service",
            resource_type="plan",
            resource_id=str(plan["id"]),
            metadata={"plan": plan["code"], "source": "default_plan"},
        )
    # Email verification delivery is "awaiting configuration" until an email provider is connected (section N).
    return issue_session(session, user=user, membership=membership, mfa=False)


def login(session: Session, data: LoginIn, meta: RequestMeta) -> TokenOut:
    user = session.scalar(select(User).where(User.email == data.email))
    ok = verify_password(data.password, user.password_hash if user else None)
    if user and user.locked_until and user.locked_until > _now():
        ok = False
    if not user or not ok or user.status != "active":
        if user:
            user.failed_login_count += 1
            if user.failed_login_count >= MAX_FAILED:
                user.locked_until = _now() + timedelta(minutes=LOCK_MINUTES)
                user.failed_login_count = 0
        audit.record(
            session,
            action="auth.login",
            result="failure",
            tenant_id=None,
            actor_user_id=user.id if user else None,
            actor_kind="anonymous",
            ip_hash=meta.ip_hash,
            correlation_id=meta.correlation_id,
        )
        session.commit()
        raise unauthorized("invalid_credentials", "Email or password is incorrect")

    mfa = False
    if user.mfa_enabled:
        if not data.mfa_code:
            raise unauthorized("mfa_required", "Enter the 6-digit code from your authenticator app")
        if not pyotp.TOTP(decrypt_secret(user.mfa_secret_enc or "")).verify(data.mfa_code, valid_window=1):
            user.failed_login_count += 1
            audit.record(
                session,
                action="auth.mfa",
                result="failure",
                tenant_id=None,
                actor_user_id=user.id,
                ip_hash=meta.ip_hash,
                correlation_id=meta.correlation_id,
            )
            session.commit()
            raise unauthorized("mfa_invalid", "The code is incorrect or expired")
        mfa = True

    set_context(session, user_id=user.id)
    q = (
        select(Membership)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == user.id, Membership.status == "active", Tenant.status == "active")
    )
    if data.tenant_id:
        q = q.where(Membership.tenant_id == data.tenant_id)
    membership = session.scalar(q.order_by(Membership.created_at).limit(1))
    if not membership:
        raise unauthorized("no_active_membership", "No active organization for this account")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = func.now()
    tokens = issue_session(session, user=user, membership=membership, mfa=mfa)
    audit.record(
        session,
        action="auth.login",
        result="success",
        tenant_id=membership.tenant_id,
        actor_user_id=user.id,
        ip_hash=meta.ip_hash,
        correlation_id=meta.correlation_id,
        metadata={"mfa": mfa},
    )
    return tokens


def refresh(session: Session, raw: str, meta: RequestMeta) -> TokenOut:
    h = token_hash(raw)
    owner = session.execute(text("select tenant_id, user_id from lookup_refresh_token(:h)"), {"h": h}).first()
    if not owner:
        raise unauthorized("invalid_refresh", "Session expired. Sign in again.")
    set_context(session, tenant_id=owner.tenant_id, user_id=owner.user_id)
    rt = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == h).with_for_update())
    if rt is None:
        raise unauthorized("invalid_refresh", "Session expired. Sign in again.")
    if rt.revoked_at is not None:
        # Reuse of a rotated token: assume theft, revoke the whole family.
        session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == rt.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        audit.record(
            session,
            action="auth.refresh_reuse",
            result="denied",
            tenant_id=rt.tenant_id,
            actor_user_id=rt.user_id,
            ip_hash=meta.ip_hash,
            correlation_id=meta.correlation_id,
        )
        session.commit()
        raise unauthorized("refresh_reused", "Session revoked for safety. Sign in again.")
    if rt.expires_at <= _now():
        raise unauthorized("invalid_refresh", "Session expired. Sign in again.")

    user = session.get(User, rt.user_id)
    membership = session.get(Membership, rt.membership_id)
    tenant = session.get(Tenant, rt.tenant_id)
    if (
        not user
        or user.status != "active"
        or not membership
        or membership.status != "active"
        or not tenant
        or tenant.status != "active"
    ):
        rt.revoked_at = _now()
        session.commit()
        raise unauthorized("session_invalid", "Session is no longer valid")

    rt.revoked_at = _now()
    tokens = issue_session(session, user=user, membership=membership, mfa=rt.mfa, family_id=rt.family_id)
    rt.replaced_by = session.scalar(
        select(RefreshToken.id).where(RefreshToken.token_hash == token_hash(tokens.refresh_token))
    )
    return tokens


def revoke_family(session: Session, family_id: UUID) -> None:
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def revoke_all_for_user_everywhere(session: Session, user_id: UUID) -> int:
    """Revoke the caller's sessions in every tenant. RLS limits normal updates to the current tenant, so this
    goes through a SECURITY DEFINER function that only acts when user_id is the authenticated user."""
    return int(session.execute(text("select revoke_my_sessions(:u)"), {"u": user_id}).scalar_one())


def revoke_all_for_user_in_tenant(session: Session, user_id: UUID) -> None:
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
