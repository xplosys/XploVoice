# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Append-only, hash-chained audit trail (HLD v1.3 section 10, LLD v1.3 section 4).

Each event's hash covers its content plus the previous event's hash for the same tenant (or the platform
chain when tenant_id is null). A per-chain advisory lock keeps the chain linear under concurrency.
Never put secrets, passwords, tokens, transcripts or PHI in `metadata`.
"""

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

FORBIDDEN_KEYS = {"password", "token", "refresh_token", "access_token", "secret", "mfa_secret", "code"}


def _clean(meta: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in meta.items() if k.lower() not in FORBIDDEN_KEYS}


def record(
    session: Session,
    *,
    action: str,
    result: str,
    tenant_id: UUID | None,
    actor_user_id: UUID | None = None,
    actor_kind: str = "user",
    resource_type: str | None = None,
    resource_id: str | None = None,
    reason: str | None = None,
    ip_hash: str | None = None,
    correlation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    meta = _clean(metadata or {})
    chain = str(tenant_id) if tenant_id else "platform"
    session.execute(text("select pg_advisory_xact_lock(hashtext(:c))"), {"c": "audit:" + chain})
    prev = session.execute(
        text("select event_hash from audit_log where tenant_id is not distinct from :t order by id desc limit 1"),
        {"t": tenant_id},
    ).scalar()
    body = json.dumps(
        {
            "tenant": str(tenant_id) if tenant_id else None,
            "actor": str(actor_user_id) if actor_user_id else None,
            "kind": actor_kind,
            "action": action,
            "rtype": resource_type,
            "rid": resource_id,
            "result": result,
            "reason": reason,
            "meta": meta,
            "prev": prev,
        },
        sort_keys=True,
        default=str,
    )
    event_hash = hashlib.sha256(body.encode()).hexdigest()
    session.execute(
        text(
            "insert into audit_log (tenant_id, actor_user_id, actor_kind, action, resource_type, resource_id, "
            "result, reason, ip_hash, correlation_id, metadata, prev_hash, event_hash) values "
            "(:t, :a, :k, :act, :rt, :rid, :res, :reason, :ip, :cid, cast(:meta as jsonb), :prev, :h)"
        ),
        {
            "t": tenant_id,
            "a": actor_user_id,
            "k": actor_kind,
            "act": action,
            "rt": resource_type,
            "rid": resource_id,
            "res": result,
            "reason": reason,
            "ip": ip_hash,
            "cid": correlation_id,
            "meta": json.dumps(meta, default=str),
            "prev": prev,
            "h": event_hash,
        },
    )
