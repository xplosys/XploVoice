# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Security control tests (M25). Each test reads the live database catalog or configuration and reports pass or
fail with what it saw, so the evidence is the system's actual state, not a statement about it. A run is stored as
platform evidence (`compliance_evidence`, kind control_test) with the commit it ran on; the activation gate needs
a passing run from the last 30 days."""

from collections.abc import Callable
from dataclasses import asdict, dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ..m03_ai.models import Provider
from ..m21_vendors.service import ai_provider_eligible

APPEND_ONLY = (
    "audit_log",
    "phi_access_audit_logs",
    "breach_assessments",
    "vendor_compliance_records",
    "call_events",
    "transcript_segments",
    "charge_ledger",
)


@dataclass
class Result:
    key: str
    name: str
    passed: bool
    detail: str


def rls_forced(s: Session) -> Result:
    rows = s.execute(
        text(
            "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'public' and c.relkind = 'r' "
            "and exists (select 1 from pg_attribute a where a.attrelid = c.oid and a.attname = 'tenant_id' "
            "and not a.attisdropped) and not (c.relrowsecurity and c.relforcerowsecurity) order by 1"
        )
    ).all()
    tables = s.scalar(
        text(
            "select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'public' and c.relkind = 'r' and exists (select 1 from pg_attribute a "
            "where a.attrelid = c.oid and a.attname = 'tenant_id' and not a.attisdropped)"
        )
    )
    bad = [r[0] for r in rows]
    return Result(
        "rls_forced",
        "Row-level security is forced on every tenant table",
        not bad,
        f"{tables} tenant tables checked." if not bad else "Not forced: " + ", ".join(bad),
    )


def runtime_role(s: Session) -> Result:
    row = s.execute(text("select rolname, rolsuper, rolbypassrls from pg_roles where rolname = current_user")).one()
    ok = not row.rolsuper and not row.rolbypassrls
    return Result(
        "runtime_role",
        "The application's database role cannot bypass row-level security",
        ok,
        f"Role {row.rolname}: superuser={row.rolsuper}, bypassrls={row.rolbypassrls}.",
    )


def append_only(s: Session) -> Result:
    bad = []
    for t in APPEND_ONLY:
        r = s.execute(
            text(
                "select has_table_privilege(current_user, :t, 'UPDATE') as u, "
                "has_table_privilege(current_user, :t, 'DELETE') as d"
            ),
            {"t": t},
        ).one()
        if r.u or r.d:
            bad.append(t)
    return Result(
        "append_only",
        "Audit, PHI access and ledger tables are append-only for the application",
        not bad,
        f"{len(APPEND_ONLY)} tables checked." if not bad else "Can be changed: " + ", ".join(bad),
    )


def purge_guarded(s: Session) -> Result:
    row = s.execute(
        text(
            "select p.prosecdef, pg_get_userbyid(p.proowner) as owner, "
            "has_function_privilege('public', p.oid, 'EXECUTE') as public_exec "
            "from pg_proc p where p.proname = 'purge_call_content'"
        )
    ).first()
    ok = bool(row and row.prosecdef and not row.public_exec)
    return Result(
        "purge_guarded",
        "Call content can only be purged through the guarded function",
        ok,
        "Security definer, owner " + str(row.owner) + ", not executable by public."
        if ok and row
        else "Missing or open.",
    )


def phi_vendors(s: Session) -> Result:
    bad = [
        p.key
        for p in s.scalars(select(Provider).where(Provider.phi_eligible.is_(True)))
        if not ai_provider_eligible(s, p).ok
    ]
    return Result(
        "phi_vendors",
        "Every provider approved for PHI has a signed, unexpired BAA on record",
        not bad,
        "No provider without a BAA in force is approved for PHI." if not bad else "No BAA in force: " + ", ".join(bad),
    )


def secrets(_: Session) -> Result:
    st = get_settings()
    if not st.is_production_like:
        return Result(
            "secrets",
            "Encryption and signing keys are configured",
            True,
            f"{st.environment}: development keys allowed; staging and production refuse to start without real keys.",
        )
    ok = bool(st.encryption_keys) and not st.jwt_secret.startswith("dev-only")
    return Result("secrets", "Encryption and signing keys are configured", ok, "Configured." if ok else "Missing.")


TESTS: tuple[Callable[[Session], Result], ...] = (
    rls_forced,
    runtime_role,
    append_only,
    purge_guarded,
    phi_vendors,
    secrets,
)


def run(s: Session) -> dict:
    results = [t(s) for t in TESTS]
    st = get_settings()
    return {
        "passed": all(r.passed for r in results),
        "results": [asdict(r) for r in results],
        "commit_sha": st.commit_sha,
        "environment": st.environment,
    }
