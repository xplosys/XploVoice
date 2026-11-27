# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""PHI access log (M23, LLD v1.3 section 9). Every read of PHI in a healthcare organisation, allowed or refused,
adds a row: who, what record (by id), why, and the request's correlation id. Rows hold no PHI and can't be
changed or removed by the application."""

from typing import Any

from ...core.context import Ctx
from ..m19_healthcare.models import PhiAccess


def log(
    ctx: Ctx,
    action: str,
    resource_type: str,
    resource_id: str | None,
    *,
    allowed: bool = True,
    purpose: str = "",
    reason: str | None = None,
) -> None:
    ctx.session.add(
        PhiAccess(
            tenant_id=ctx.tenant.id,
            actor_user_id=ctx.user.id,
            actor_kind="user",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            purpose=purpose[:200],
            result="allowed" if allowed else "denied",
            reason=reason,
            correlation_id=ctx.meta.correlation_id,
            ip_hash=ctx.meta.ip_hash,
        )
    )
    ctx.session.flush()


def log_system(s: Any, tenant_id: Any, action: str, resource_type: str, resource_id: str | None, purpose: str) -> None:
    s.add(
        PhiAccess(
            tenant_id=tenant_id,
            actor_kind="system",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            purpose=purpose[:200],
            result="allowed",
        )
    )
