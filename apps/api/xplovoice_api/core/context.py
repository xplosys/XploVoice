# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Per-request security context.

The tenant comes only from a server-signed access token, and is re-validated against the database on every
request: user active, membership active, tenant active, session not revoked. Then RLS context is set for the
request transaction. A tenant id in a URL, header or body is never used for authorization.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..modules.m01_identity.models import RefreshToken, User
from ..modules.m02_tenant.models import Membership, Tenant
from . import audit
from .db import get_engine, set_context
from .errors import forbidden, unauthorized
from .permissions import Perm, has
from .security import decode_access_token, ip_hash

bearer = HTTPBearer(auto_error=False)


@dataclass
class RequestMeta:
    correlation_id: str | None
    ip_hash: str | None


@dataclass
class Ctx:
    session: Session
    user: User
    membership: Membership
    tenant: Tenant
    session_id: UUID
    mfa: bool
    meta: RequestMeta

    def commit(self) -> None:
        """Commits mid-request (for example before a carrier request) and keeps the RLS context, which is per
        transaction."""
        self.session.commit()
        set_context(self.session, tenant_id=self.tenant.id, user_id=self.user.id)

    def require(self, perm: Perm) -> None:
        if not has(self.membership.role, perm):
            audit.record(
                self.session,
                action="authz.denied",
                result="denied",
                tenant_id=self.tenant.id,
                actor_user_id=self.user.id,
                resource_type="permission",
                resource_id=perm.value,
                ip_hash=self.meta.ip_hash,
                correlation_id=self.meta.correlation_id,
            )
            self.session.commit()
            raise forbidden()

    def audit(
        self,
        action: str,
        *,
        result: str = "success",
        resource_type: str | None = None,
        resource_id: str | None = None,
        reason: str | None = None,
        **meta: object,
    ) -> None:
        audit.record(
            self.session,
            action=action,
            result=result,
            tenant_id=self.tenant.id,
            actor_user_id=self.user.id,
            resource_type=resource_type,
            resource_id=resource_id,
            reason=reason,
            ip_hash=self.meta.ip_hash,
            correlation_id=self.meta.correlation_id,
            metadata=dict(meta),
        )


def request_meta(request: Request) -> RequestMeta:
    client = request.client.host if request.client else None
    return RequestMeta(correlation_id=getattr(request.state, "correlation_id", None), ip_hash=ip_hash(client))


def open_session() -> Session:
    s = Session(bind=get_engine(), expire_on_commit=False)
    s.begin()
    return s


def get_ctx(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Iterator[Ctx]:
    if creds is None or creds.scheme.lower() != "bearer":
        raise unauthorized()
    try:
        claims = decode_access_token(creds.credentials)
        user_id, tenant_id, sid = UUID(claims["sub"]), UUID(claims["tid"]), UUID(claims["sid"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise unauthorized("invalid_token", "Invalid or expired token") from None

    session = open_session()
    try:
        set_context(session, tenant_id=tenant_id, user_id=user_id)
        user = session.get(User, user_id)
        membership = session.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant_id, Membership.user_id == user_id, Membership.status == "active"
            )
        )
        tenant = session.get(Tenant, tenant_id)
        live = session.scalar(
            select(RefreshToken.id).where(RefreshToken.family_id == sid, RefreshToken.revoked_at.is_(None)).limit(1)
        )
        if not user or user.status != "active" or not membership or not tenant or live is None:
            raise unauthorized("session_invalid", "Session is no longer valid")
        if tenant.status != "active":
            raise forbidden("This organization is suspended")
        ctx = Ctx(
            session=session,
            user=user,
            membership=membership,
            tenant=tenant,
            session_id=sid,
            mfa="otp" in claims.get("amr", []),
            meta=request_meta(request),
        )
        yield ctx
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def require(perm: Perm) -> Callable[[Ctx], Ctx]:
    def dep(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        ctx.require(perm)
        return ctx

    return dep


def enable_platform_admin(session: Session) -> None:
    session.execute(text("select set_config('app.platform_admin', 'on', true)"))
