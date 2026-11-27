# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Provider selection (M03). Builds the ordered list of candidates for a request from the tenant's routes (or the
platform defaults when the tenant has none), then removes any candidate that cannot serve it. Every exclusion
carries a reason so the UI can explain why a provider was skipped."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import null, select
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...core.security import decrypt_secret
from . import breaker
from .adapters import adapter_for
from .adapters.base import Endpoint
from .models import Credential, Model, PlatformRoute, Provider, TenantRoute


@dataclass
class Candidate:
    provider: Provider
    model: Model
    account: str  # managed | customer
    credential_id: UUID | None
    endpoint: Endpoint


@dataclass
class Skipped:
    provider: str
    model: str
    reason: str


def language_ok(model: Model, language: str | None) -> bool:
    if not language or not model.languages:
        return True
    base = language.split("-")[0]
    return language in model.languages or base in model.languages


def managed_endpoint(provider: Provider) -> tuple[Endpoint | None, str | None]:
    s = get_settings()
    if provider.hosting == "dev_only":
        if s.is_production_like:
            return None, "development-only provider"
        return Endpoint(base_url="mock://", secret=None), None
    if provider.hosting == "self_hosted":
        url = s.self_hosted_urls.get(provider.key) or provider.base_url
        return (Endpoint(base_url=url.rstrip("/"), secret=None), None) if url else (None, "awaiting configuration")
    key = s.provider_keys.get(provider.key)
    if not key or not provider.managed_available or not provider.base_url:
        return None, "awaiting configuration (no XploVoice-managed account)"
    return Endpoint(base_url=provider.base_url.rstrip("/"), secret=key), None


def candidates(
    session: Session,
    *,
    kind: str,
    language: str | None = None,
    need_streaming: bool = False,
    need_tools: bool = False,
    phi: bool = False,
    prefer: UUID | None = None,
) -> tuple[list[Candidate], list[Skipped]]:
    """Must run inside a tenant context (RLS limits tenant routes and credentials to the caller's tenant).
    `prefer` (an agent's chosen model) moves that route to the front; the rest stay as failover. A preferred
    model that is not one of the routes is ignored, so an agent can never reach a model the tenant has not
    routed.

    In a healthcare organisation (M19) every request is treated as carrying PHI, whatever the caller passed:
    only providers with a signed, unexpired BAA on record are candidates (M21), and customer-owned keys are
    skipped because XploVoice cannot see the customer's own agreement with that vendor."""
    from ..m19_healthcare.mode import phi_mode
    from ..m21_vendors.service import ai_provider_eligible

    healthcare = phi_mode(session)
    phi = phi or healthcare
    rows = session.execute(
        select(TenantRoute.model_id, TenantRoute.credential_id)
        .where(TenantRoute.kind == kind, TenantRoute.enabled.is_(True))
        .order_by(TenantRoute.priority)
    ).all()
    if not rows:
        rows = session.execute(
            select(PlatformRoute.model_id, null())
            .where(PlatformRoute.kind == kind, PlatformRoute.enabled.is_(True))
            .order_by(PlatformRoute.priority)
        ).all()
    if prefer is not None:
        rows = sorted(rows, key=lambda r: r[0] != prefer)  # stable: keeps the tenant's order for the rest
    out: list[Candidate] = []
    skipped: list[Skipped] = []
    for model_id, credential_id in rows:
        model = session.get(Model, model_id)
        provider = session.get(Provider, model.provider_id) if model else None
        if not model or not provider:
            continue

        def skip(reason: str, p: Provider = provider, m: Model = model) -> None:
            skipped.append(Skipped(p.name, m.display_name, reason))

        if provider.status != "active" or model.status != "active":
            skip("disabled by XploVoice")
            continue
        if adapter_for(provider.adapter, kind) is None:
            skip(f"provider has no {kind} adapter")
            continue
        if not language_ok(model, language):
            skip(f"does not support {language}")
            continue
        if need_streaming and not model.streaming:
            skip("no streaming support")
            continue
        if need_tools and not model.function_calling:
            skip("no function calling")
            continue
        if phi:
            eligible = ai_provider_eligible(session, provider)
            if not eligible.ok:
                skip(eligible.reason)
                continue
        if credential_id and healthcare:
            skip("customer-owned keys are not used in healthcare mode")
            continue
        if credential_id:
            cred = session.get(Credential, credential_id)
            if not cred or cred.status != "active" or cred.provider_id != provider.id:
                skip("your API key was revoked")
                continue
            if not provider.customer_keys_allowed or not provider.base_url:
                skip("customer-owned keys are not allowed for this provider")
                continue
            ep = Endpoint(base_url=provider.base_url.rstrip("/"), secret=decrypt_secret(cred.secret_enc))
            account = "customer"
        else:
            ep_or_none, why = managed_endpoint(provider)
            if ep_or_none is None:
                skip(why or "unavailable")
                continue
            ep, account = ep_or_none, "managed"
        if breaker.state(provider.key) == "open":
            skip("temporarily unavailable (circuit open)")
            continue
        out.append(Candidate(provider, model, account, credential_id, ep))
    return out, skipped
