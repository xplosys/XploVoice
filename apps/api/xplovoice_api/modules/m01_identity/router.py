# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import pyotp
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core import ratelimit
from ...core.config import get_settings
from ...core.context import Ctx, get_ctx, request_meta
from ...core.errors import bad_request, conflict, unauthorized
from ...core.permissions import ROLE_PERMISSIONS
from ...core.public import get_public_session
from ...core.security import decrypt_secret, encrypt_secret, hash_password, verify_password
from ..m02_tenant.models import Membership
from . import service
from .schemas import (
    ChangePasswordIn,
    LoginIn,
    MeOut,
    MfaCodeIn,
    MfaDisableIn,
    MfaEnrollOut,
    RefreshIn,
    RegisterIn,
    SwitchTenantIn,
    TokenOut,
)

router = APIRouter(prefix="/v1/auth", tags=["M01 Identity & Access"])


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, request: Request, session: Session = Depends(get_public_session)) -> TokenOut:
    meta = request_meta(request)
    ratelimit.hit(f"register:{meta.ip_hash}", 5)
    return service.register(session, data, meta)


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, request: Request, session: Session = Depends(get_public_session)) -> TokenOut:
    meta = request_meta(request)
    limit = get_settings().login_rate_limit_per_minute
    ratelimit.hit(f"login:ip:{meta.ip_hash}", limit * 3)
    ratelimit.hit(f"login:email:{data.email.lower()}", limit)
    return service.login(session, data, meta)


@router.post("/refresh", response_model=TokenOut)
def refresh(data: RefreshIn, request: Request, session: Session = Depends(get_public_session)) -> TokenOut:
    return service.refresh(session, data.refresh_token, request_meta(request))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(ctx: Ctx = Depends(get_ctx)) -> None:
    service.revoke_family(ctx.session, ctx.session_id)
    ctx.audit("auth.logout")


@router.post("/switch-tenant", response_model=TokenOut)
def switch_tenant(data: SwitchTenantIn, ctx: Ctx = Depends(get_ctx)) -> TokenOut:
    from ...core.db import set_context

    ctx.audit("auth.switch_tenant", resource_type="tenant", resource_id=str(data.tenant_id))
    service.revoke_family(ctx.session, ctx.session_id)  # old tenant session ends (needs old tenant context)
    set_context(ctx.session, user_id=ctx.user.id)
    membership = ctx.session.scalar(
        select(Membership).where(
            Membership.user_id == ctx.user.id, Membership.tenant_id == data.tenant_id, Membership.status == "active"
        )
    )
    if not membership:
        ctx.session.rollback()
        raise unauthorized("no_membership", "You are not a member of that organization")
    return service.issue_session(ctx.session, user=ctx.user, membership=membership, mfa=ctx.mfa)


@router.get("/me", response_model=MeOut)
def me(ctx: Ctx = Depends(get_ctx)) -> MeOut:
    return MeOut(
        user_id=ctx.user.id,
        email=ctx.user.email,
        display_name=ctx.user.display_name,
        email_verified=ctx.user.email_verified_at is not None,
        mfa_enabled=ctx.user.mfa_enabled,
        is_platform_admin=ctx.user.is_platform_admin,
        tenant_id=ctx.tenant.id,
        tenant_name=ctx.tenant.name,
        role=ctx.membership.role,
        permissions=sorted(p.value for p in ROLE_PERMISSIONS[ctx.membership.role]),
    )


@router.post("/mfa/enroll", response_model=MfaEnrollOut)
def mfa_enroll(ctx: Ctx = Depends(get_ctx)) -> MfaEnrollOut:
    if ctx.user.mfa_enabled:
        raise conflict("mfa_already_enabled", "MFA is already enabled")
    secret = pyotp.random_base32()
    ctx.user.mfa_secret_enc = encrypt_secret(secret)
    uri = pyotp.TOTP(secret).provisioning_uri(name=ctx.user.email, issuer_name=get_settings().mfa_issuer)
    ctx.audit("auth.mfa_enroll_started", resource_type="user", resource_id=str(ctx.user.id))
    return MfaEnrollOut(secret=secret, otpauth_uri=uri)


@router.post("/mfa/verify", status_code=status.HTTP_204_NO_CONTENT)
def mfa_verify(data: MfaCodeIn, ctx: Ctx = Depends(get_ctx)) -> None:
    if not ctx.user.mfa_secret_enc:
        raise bad_request("mfa_not_started", "Start MFA enrollment first")
    if not pyotp.TOTP(decrypt_secret(ctx.user.mfa_secret_enc)).verify(data.code, valid_window=1):
        raise bad_request("mfa_invalid", "The code is incorrect or expired")
    from sqlalchemy import func

    ctx.user.mfa_enabled_at = func.now()
    ctx.audit("auth.mfa_enabled", resource_type="user", resource_id=str(ctx.user.id))


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
def mfa_disable(data: MfaDisableIn, ctx: Ctx = Depends(get_ctx)) -> None:
    if (
        not ctx.user.mfa_enabled
        or not verify_password(data.password, ctx.user.password_hash)
        or not pyotp.TOTP(decrypt_secret(ctx.user.mfa_secret_enc or "")).verify(data.code, valid_window=1)
    ):
        raise unauthorized("reauth_failed", "Password or code is incorrect")
    ctx.user.mfa_enabled_at = None
    ctx.user.mfa_secret_enc = None
    ctx.audit("auth.mfa_disabled", resource_type="user", resource_id=str(ctx.user.id))


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(data: ChangePasswordIn, ctx: Ctx = Depends(get_ctx)) -> None:
    if not verify_password(data.current_password, ctx.user.password_hash):
        raise unauthorized("reauth_failed", "Current password is incorrect")
    ctx.user.password_hash = hash_password(data.new_password)
    service.revoke_all_for_user_in_tenant(ctx.session, ctx.user.id)
    ctx.audit("auth.password_changed", resource_type="user", resource_id=str(ctx.user.id))
