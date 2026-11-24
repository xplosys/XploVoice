# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Role-based permissions (RBAC). Roles follow the HLD personas; checks happen in the API, never only in the UI.
Healthcare roles (HLD v1.3 section 6) are added with M19 in Phase 8."""

from enum import StrEnum


class Perm(StrEnum):
    TENANT_READ = "tenant:read"
    TENANT_MANAGE = "tenant:manage"
    MEMBERS_READ = "members:read"
    MEMBERS_MANAGE = "members:manage"
    AUDIT_READ = "audit:read"
    AGENTS_READ = "agents:read"
    AGENTS_MANAGE = "agents:manage"
    CALLS_READ = "calls:read"
    BILLING_MANAGE = "billing:manage"


ROLE_PERMISSIONS: dict[str, frozenset[Perm]] = {
    "owner": frozenset(Perm),
    "admin": frozenset(Perm) - {Perm.BILLING_MANAGE},
    "agent_designer": frozenset(
        {Perm.TENANT_READ, Perm.MEMBERS_READ, Perm.AGENTS_READ, Perm.AGENTS_MANAGE, Perm.CALLS_READ}
    ),
    "operator": frozenset({Perm.TENANT_READ, Perm.MEMBERS_READ, Perm.AGENTS_READ, Perm.CALLS_READ}),
    "viewer": frozenset({Perm.TENANT_READ, Perm.AGENTS_READ, Perm.CALLS_READ}),
}

ROLES = tuple(ROLE_PERMISSIONS)
ROLE_RANK = {"viewer": 0, "operator": 1, "agent_designer": 2, "admin": 3, "owner": 4}


def has(role: str, perm: Perm) -> bool:
    return perm in ROLE_PERMISSIONS.get(role, frozenset())
