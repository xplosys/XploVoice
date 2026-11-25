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
    AGENTS_PUBLISH = "agents:publish"  # publish, roll back, pause, resume: changes what live callers reach
    CALLS_READ = "calls:read"
    CALLS_TEST = "calls:test"
    BILLING_MANAGE = "billing:manage"
    AI_READ = "ai:read"
    AI_MANAGE = "ai:manage"
    AI_TEST = "ai:test"
    USAGE_READ = "usage:read"
    # Phase 5
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_MANAGE = "knowledge:manage"
    WORKFLOWS_READ = "workflows:read"  # calendars, appointments, leads, follow-ups
    WORKFLOWS_MANAGE = "workflows:manage"
    SUPPORT_READ = "support:read"  # tickets and the notification log
    SUPPORT_MANAGE = "support:manage"
    NOTIFICATIONS_MANAGE = "notifications:manage"  # write and approve the messages agents may send
    TOOLS_MANAGE = "tools:manage"  # tenant tool policies: enabled, needs approval
    TOOLS_APPROVE = "tools:approve"  # approve or deny a sensitive action an agent asked for
    INTEGRATIONS_MANAGE = "integrations:manage"


ROLE_PERMISSIONS: dict[str, frozenset[Perm]] = {
    "owner": frozenset(Perm),
    "admin": frozenset(Perm) - {Perm.BILLING_MANAGE},
    "agent_designer": frozenset(
        {
            Perm.TENANT_READ,
            Perm.MEMBERS_READ,
            Perm.AGENTS_READ,
            Perm.AGENTS_MANAGE,
            Perm.CALLS_READ,
            Perm.CALLS_TEST,
            Perm.AI_READ,
            Perm.AI_TEST,
            Perm.KNOWLEDGE_READ,
            Perm.KNOWLEDGE_MANAGE,
            Perm.WORKFLOWS_READ,
            Perm.SUPPORT_READ,
        }
    ),
    # Front-office staff: work the appointments, leads, follow-ups and tickets the agents create.
    "operator": frozenset(
        {
            Perm.TENANT_READ,
            Perm.MEMBERS_READ,
            Perm.AGENTS_READ,
            Perm.CALLS_READ,
            Perm.AI_READ,
            Perm.KNOWLEDGE_READ,
            Perm.WORKFLOWS_READ,
            Perm.WORKFLOWS_MANAGE,
            Perm.SUPPORT_READ,
            Perm.SUPPORT_MANAGE,
            Perm.TOOLS_APPROVE,
        }
    ),
    "viewer": frozenset(
        {
            Perm.TENANT_READ,
            Perm.AGENTS_READ,
            Perm.CALLS_READ,
            Perm.AI_READ,
            Perm.KNOWLEDGE_READ,
            Perm.WORKFLOWS_READ,
            Perm.SUPPORT_READ,
        }
    ),
}

ROLES = tuple(ROLE_PERMISSIONS)
ROLE_RANK = {"viewer": 0, "operator": 1, "agent_designer": 2, "admin": 3, "owner": 4}


def has(role: str, perm: Perm) -> bool:
    return perm in ROLE_PERMISSIONS.get(role, frozenset())
