# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""The healthcare activation gate (LLD v1.3 section 6). Healthcare mode turns on only when every check passes, and
only by a platform admin who is not the person who asked for it. The checks are evaluated live, so the tenant's
Healthcare page and the admin console always show the same answer, and the result is stored with the activation.

Must run in the organisation's RLS context (the admin console switches to it)."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ..m01_identity.models import User
from ..m02_tenant.models import Membership, Tenant
from .models import Evidence, HealthcarePolicy, HealthcareProfile, RetentionPolicy


@dataclass
class Check:
    key: str
    label: str
    ok: bool
    detail: str


def latest_control_run(s: Session) -> Evidence | None:
    return s.scalar(
        select(Evidence)
        .where(Evidence.tenant_id.is_(None), Evidence.kind == "control_test", Evidence.status == "valid")
        .order_by(Evidence.created_at.desc())
        .limit(1)
    )


def customer_baa(s: Session, tenant_id: Any) -> Evidence | None:
    today = datetime.now(UTC).date()
    return s.scalar(
        select(Evidence)
        .where(
            Evidence.tenant_id == tenant_id,
            Evidence.kind == "customer_baa",
            Evidence.status == "valid",
            (Evidence.valid_until.is_(None)) | (Evidence.valid_until >= today),
        )
        .order_by(Evidence.created_at.desc())
        .limit(1)
    )


def evaluate(s: Session, tenant: Tenant, prof: HealthcareProfile | None) -> list[Check]:
    from ..m03_ai.routing import candidates

    settings = get_settings()
    out: list[Check] = []

    def add(key: str, label: str, ok: bool, yes: str, no: str) -> None:
        out.append(Check(key, label, ok, yes if ok else no))

    add(
        "platform_enabled",
        "Healthcare Mode is available on this platform",
        settings.healthcare_enabled,
        "Turned on by Xplosys.",
        "Xplosys has not turned Healthcare Mode on for this platform yet.",
    )
    add(
        "requested",
        "The organisation asked for Healthcare Mode",
        prof is not None and prof.status != "withdrawn",
        "Requested.",
        "Ask for Healthcare Mode on the Healthcare page.",
    )
    add(
        "jurisdiction",
        "US organisation",
        tenant.country_code == "US",
        "Country: United States.",
        "Healthcare Mode is offered to US organisations only.",
    )
    synthetic_ok = settings.environment == "production" or bool(prof and prof.synthetic_data_only)
    add(
        "synthetic_data",
        "Synthetic data only outside production",
        synthetic_ok,
        "Production, or synthetic data confirmed." if settings.environment == "production" else "Confirmed.",
        "Outside production, confirm that only synthetic (made-up) data will be used.",
    )
    baa = customer_baa(s, tenant.id)
    add(
        "customer_baa",
        "Business associate agreement with Xplosys",
        baa is not None,
        f"On record: {baa.title}" + (f" (until {baa.valid_until.isoformat()})" if baa and baa.valid_until else "")
        if baa
        else "",
        "Xplosys records your signed BAA here once it is in place.",
    )
    pol = s.scalar(
        select(HealthcarePolicy)
        .where(HealthcarePolicy.tenant_id == tenant.id, HealthcarePolicy.status == "approved")
        .order_by(HealthcarePolicy.version.desc())
        .limit(1)
    )
    add(
        "policy",
        "Healthcare policy approved",
        pol is not None,
        f"Version {pol.version} approved." if pol else "",
        "Write a policy version and have a second person approve it.",
    )
    ret = s.scalar(
        select(RetentionPolicy).where(
            RetentionPolicy.tenant_id == tenant.id, RetentionPolicy.resource_type == "call_content"
        )
    )
    add(
        "retention",
        "Retention schedule for call content",
        ret is not None,
        f"Call content kept {ret.retain_days} days." if ret else "",
        "Set how long transcripts and call details are kept, under Retention.",
    )
    officers = (
        s.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.tenant_id == tenant.id, Membership.status == "active", Membership.role == "privacy_officer"
            )
        )
        or 0
    )
    add(
        "privacy_officer",
        "A privacy officer is named",
        officers > 0,
        f"{officers} privacy officer(s).",
        "Invite someone with the Privacy officer role on the Team page.",
    )
    no_mfa = (
        s.scalar(
            select(func.count())
            .select_from(Membership)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == tenant.id, Membership.status == "active", User.mfa_enabled_at.is_(None))
        )
        or 0
    )
    add(
        "mfa",
        "Every member uses two-factor authentication",
        no_mfa == 0,
        "All members have it on.",
        f"{no_mfa} member(s) still need to turn on two-factor authentication.",
    )
    missing = [k.upper() for k in ("llm", "stt", "tts") if not candidates(s, kind=k, phi=True)[0]]
    add(
        "phi_providers",
        "AI providers with a signed BAA for every step",
        not missing,
        "Language model, speech-to-text and text-to-speech all have an approved provider.",
        "No approved provider for: " + ", ".join(missing) + ". Route these to providers with a signed BAA.",
    )
    run = latest_control_run(s)
    max_age = timedelta(days=settings.healthcare_control_test_max_age_days)
    fresh = run is not None and datetime.now(UTC) - run.created_at <= max_age
    passed = bool(run and run.details.get("passed"))
    add(
        "control_tests",
        "Platform security control tests passed recently",
        fresh and passed,
        f"Passed on {run.created_at.date().isoformat()}." if run else "",
        f"No passing control-test run in the last {settings.healthcare_control_test_max_age_days} days."
        if not (run and not passed)
        else "The latest control-test run failed.",
    )
    return out


def as_dicts(checks: list[Check]) -> list[dict]:
    return [asdict(c) for c in checks]
