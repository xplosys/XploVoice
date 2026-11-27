# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Is healthcare mode on for the organisation in the current RLS context? Small and dependency-free, because the
AI router, billing admission, the call APIs, webhooks and the engine bootstrap all ask.

PHI mode is on while the profile is 'active' or 'suspended': suspending stops new calls but never relaxes a
protection. A profile that is only 'requested' changes nothing."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import HealthcarePolicy, HealthcareProfile

PHI_STATUSES = ("active", "suspended")


def _mine():  # type: ignore[no-untyped-def]
    # RLS already limits rows to the tenant; the explicit filter keeps a platform-admin context (which may read
    # every profile) from seeing another organisation's.
    return HealthcareProfile.tenant_id == func.app_tenant_id()


def profile(s: Session) -> HealthcareProfile | None:
    return s.scalar(select(HealthcareProfile).where(_mine()).limit(1))


def phi_mode(s: Session) -> bool:
    return (
        s.scalar(select(HealthcareProfile.id).where(_mine(), HealthcareProfile.status.in_(PHI_STATUSES)).limit(1))
        is not None
    )


def suspended(s: Session) -> bool:
    return (
        s.scalar(select(HealthcareProfile.id).where(_mine(), HealthcareProfile.status == "suspended").limit(1))
        is not None
    )


@dataclass(frozen=True)
class PolicyInForce:
    version: int | None
    recording_mode: str
    privacy_notice: str
    allow_outbound_campaigns: bool


STRICTEST = PolicyInForce(None, "off", "", False)


def policy_in_force(s: Session) -> PolicyInForce:
    """The latest approved policy version; without one, the strictest settings."""
    p = s.scalar(
        select(HealthcarePolicy)
        .where(HealthcarePolicy.tenant_id == func.app_tenant_id(), HealthcarePolicy.status == "approved")
        .order_by(HealthcarePolicy.version.desc())
        .limit(1)
    )
    if p is None:
        return STRICTEST
    return PolicyInForce(p.version, p.recording_mode, p.privacy_notice, p.allow_outbound_campaigns)


def recording_policy(s: Session, agent_policy: str) -> str:
    """What a call in this organisation may do about recording: in healthcare mode recording needs the caller's
    consent ('ask_consent') when the policy allows it at all, and is off otherwise."""
    if not phi_mode(s):
        return agent_policy
    if agent_policy == "off" or policy_in_force(s).recording_mode == "off":
        return "off"
    return "ask_consent"
