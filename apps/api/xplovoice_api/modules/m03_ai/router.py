# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Tenant API for AI providers (M03): catalog, customer-owned keys, routing, and a test playground."""

import base64
import binascii
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy import delete, select
from starlette.concurrency import run_in_threadpool

from ...core import ratelimit
from ...core.config import get_settings
from ...core.context import Ctx, require
from ...core.errors import ApiError, bad_request, not_found
from ...core.permissions import Perm
from ...core.security import decrypt_secret, encrypt_secret
from ..m15_usage import billing
from . import gateway
from .adapters import adapter_for
from .adapters.base import ChatMessage, Endpoint, LLMRequest
from .models import Credential, Model, PlatformRoute, Provider, RateCard, TenantRoute
from .routing import candidates, managed_endpoint
from .schemas import (
    ChatTestIn,
    CheckOut,
    CredentialIn,
    CredentialOut,
    Kind,
    KindRoutesOut,
    ModelOut,
    PriceOut,
    ProviderOut,
    RouteOut,
    RoutesIn,
    SpeechTestIn,
    TestOut,
    TranscribeTestIn,
)

router = APIRouter(prefix="/v1/ai", tags=["ai"])


def _visible(p: Provider) -> bool:
    return p.hosting != "dev_only" or not get_settings().is_production_like


def current_prices(ctx: Ctx, model_id: uuid.UUID) -> list[PriceOut]:
    cards = ctx.session.scalars(
        select(RateCard)
        .where(RateCard.model_id == model_id, RateCard.effective_from <= datetime.now(UTC))
        .order_by(RateCard.unit, RateCard.effective_from.desc())
    ).all()
    latest: dict[str, RateCard] = {}
    for c in cards:
        latest.setdefault(c.unit, c)
    return [
        PriceOut(
            unit=c.unit, unit_price=c.unit_price, currency=c.currency, effective_from=c.effective_from, source=c.source
        )
        for c in latest.values()
    ]


def model_out(ctx: Ctx, m: Model) -> ModelOut:
    return ModelOut(
        id=m.id,
        kind=m.kind,
        model_key=m.model_key,
        display_name=m.display_name,
        languages=m.languages,
        streaming=m.streaming,
        function_calling=m.function_calling,
        context_window=m.context_window,
        voices=m.voices,
        status=m.status,
        prices=current_prices(ctx, m.id),
    )


def managed_status(p: Provider) -> str:
    if p.hosting == "dev_only":
        return "development only"
    ep, why = managed_endpoint(p)
    return "available" if ep else (why or "unavailable")


@router.get("/catalog", response_model=list[ProviderOut])
def catalog(ctx: Ctx = Depends(require(Perm.AI_READ))) -> list[ProviderOut]:
    out = []
    for p in ctx.session.scalars(select(Provider).where(Provider.status == "active").order_by(Provider.name)):
        if not _visible(p):
            continue
        models = ctx.session.scalars(
            select(Model)
            .where(Model.provider_id == p.id, Model.status == "active")
            .order_by(Model.kind, Model.model_key)
        ).all()
        out.append(
            ProviderOut(
                id=p.id,
                key=p.key,
                name=p.name,
                hosting=p.hosting,
                kinds=p.kinds,
                regions=p.regions,
                phi_eligible=p.phi_eligible,
                customer_keys_allowed=p.customer_keys_allowed,
                managed_status=managed_status(p),
                status=p.status,
                models=[model_out(ctx, m) for m in models],
            )
        )
    return out


# ------------------------------------------------------------------ customer-owned credentials
def _cred_out(c: Credential, p: Provider) -> CredentialOut:
    return CredentialOut(
        id=c.id,
        provider_key=p.key,
        provider_name=p.name,
        label=c.label,
        secret_hint=c.secret_hint,
        status=c.status,
        last_verified_at=c.last_verified_at,
        last_error=c.last_error,
        created_at=c.created_at,
    )


@router.get("/credentials", response_model=list[CredentialOut])
def list_credentials(ctx: Ctx = Depends(require(Perm.AI_READ))) -> list[CredentialOut]:
    rows = ctx.session.execute(
        select(Credential, Provider)
        .join(Provider, Provider.id == Credential.provider_id)
        .where(Credential.tenant_id == ctx.tenant.id, Credential.status == "active")
        .order_by(Credential.created_at)
    ).all()
    return [_cred_out(c, p) for c, p in rows]


@router.post("/credentials", response_model=CredentialOut, status_code=status.HTTP_201_CREATED)
def add_credential(data: CredentialIn, ctx: Ctx = Depends(require(Perm.AI_MANAGE))) -> CredentialOut:
    p = ctx.session.scalar(select(Provider).where(Provider.key == data.provider_key, Provider.status == "active"))
    if not p or p.hosting != "cloud" or not p.customer_keys_allowed:
        raise bad_request("provider_not_allowed", "This provider does not accept your own API keys")
    secret = data.secret.strip()
    c = Credential(
        tenant_id=ctx.tenant.id,
        provider_id=p.id,
        label=data.label,
        secret_enc=encrypt_secret(secret),
        secret_hint=f"…{secret[-4:]}",
        created_by_membership_id=ctx.membership.id,
    )
    ctx.session.add(c)
    ctx.session.flush()
    ctx.session.refresh(c)
    ctx.audit("ai.credential_added", resource_type="ai_credential", resource_id=str(c.id), provider=p.key)
    return _cred_out(c, p)


def _get_cred(ctx: Ctx, cred_id: uuid.UUID) -> tuple[Credential, Provider]:
    c = ctx.session.get(Credential, cred_id)
    if not c or c.tenant_id != ctx.tenant.id or c.status != "active":
        raise not_found()
    return c, ctx.session.get(Provider, c.provider_id)


@router.post("/credentials/{cred_id}/verify", response_model=CredentialOut)
async def verify_credential(cred_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.AI_MANAGE))) -> CredentialOut:
    c, p = await run_in_threadpool(_get_cred, ctx, cred_id)
    adapter = next((a for k in p.kinds if (a := adapter_for(p.adapter, k))), None)
    ok = (
        await adapter.verify(Endpoint(base_url=(p.base_url or "").rstrip("/"), secret=decrypt_secret(c.secret_enc)))
        if adapter
        else None
    )

    def save() -> CredentialOut:
        if ok is True:
            c.last_verified_at, c.last_error = datetime.now(UTC), None
        elif ok is False:
            c.last_error = "The provider rejected this key or could not be reached"
        else:
            c.last_error = "This provider cannot be checked without making a billable request"
        ctx.audit(
            "ai.credential_verified",
            result="success" if ok else "failure",
            resource_type="ai_credential",
            resource_id=str(c.id),
        )
        return _cred_out(c, p)

    return await run_in_threadpool(save)


@router.delete("/credentials/{cred_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_credential(cred_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.AI_MANAGE))) -> Response:
    c, _ = _get_cred(ctx, cred_id)
    c.status, c.revoked_at = "revoked", datetime.now(UTC)
    c.secret_enc = encrypt_secret("revoked")  # the real key is not kept after revocation
    ctx.audit("ai.credential_revoked", resource_type="ai_credential", resource_id=str(c.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ routing
def _routes_for(ctx: Ctx, kind: str) -> KindRoutesOut:
    rows = ctx.session.scalars(
        select(TenantRoute)
        .where(TenantRoute.tenant_id == ctx.tenant.id, TenantRoute.kind == kind)
        .order_by(TenantRoute.priority)
    ).all()
    source = "organisation"
    items: list[tuple[int, uuid.UUID, uuid.UUID | None]] = [(r.priority, r.model_id, r.credential_id) for r in rows]
    if not items:
        source = "platform default"
        items = [
            (r.priority, r.model_id, None)
            for r in ctx.session.scalars(
                select(PlatformRoute)
                .where(PlatformRoute.kind == kind, PlatformRoute.enabled.is_(True))
                .order_by(PlatformRoute.priority)
            )
        ]
    out = []
    for prio, model_id, cred_id in items:
        m = ctx.session.get(Model, model_id)
        p = ctx.session.get(Provider, m.provider_id)
        cred = ctx.session.get(Credential, cred_id) if cred_id else None
        out.append(
            RouteOut(
                priority=prio,
                model_id=m.id,
                model=m.display_name,
                provider=p.name,
                credential_id=cred_id,
                credential_label=cred.label if cred else None,
            )
        )
    return KindRoutesOut(kind=kind, source=source if out else "none", routes=out)


@router.get("/routes", response_model=list[KindRoutesOut])
def get_routes(ctx: Ctx = Depends(require(Perm.AI_READ))) -> list[KindRoutesOut]:
    return [_routes_for(ctx, k) for k in ("llm", "stt", "tts")]


@router.put("/routes/{kind}", response_model=KindRoutesOut)
def set_routes(kind: Kind, data: RoutesIn, ctx: Ctx = Depends(require(Perm.AI_MANAGE))) -> KindRoutesOut:
    seen = set()
    for r in data.routes:
        m = ctx.session.get(Model, r.model_id)
        p = ctx.session.get(Provider, m.provider_id) if m else None
        if not m or m.kind != kind or m.status != "active" or not p or p.status != "active" or not _visible(p):
            raise bad_request("invalid_model", f"Choose an active {kind} model from the catalog")
        if r.credential_id:
            c = ctx.session.get(Credential, r.credential_id)
            if not c or c.tenant_id != ctx.tenant.id or c.status != "active" or c.provider_id != p.id:
                raise bad_request("invalid_credential", f"That API key is not a {p.name} key in this organisation")
        if (r.model_id, r.credential_id) in seen:
            raise bad_request("duplicate_route", "Each model and key combination can appear only once")
        seen.add((r.model_id, r.credential_id))
    ctx.session.execute(delete(TenantRoute).where(TenantRoute.tenant_id == ctx.tenant.id, TenantRoute.kind == kind))
    for i, r in enumerate(data.routes, start=1):
        ctx.session.add(
            TenantRoute(
                tenant_id=ctx.tenant.id, kind=kind, priority=i, model_id=r.model_id, credential_id=r.credential_id
            )
        )
    ctx.session.flush()
    ctx.audit("ai.routes_updated", resource_type="ai_routes", resource_id=kind, count=len(data.routes))
    return _routes_for(ctx, kind)


@router.get("/routes/{kind}/check", response_model=CheckOut)
def check_routes(kind: Kind, language: str | None = None, ctx: Ctx = Depends(require(Perm.AI_READ))) -> CheckOut:
    usable, skipped = candidates(ctx.session, kind=kind, language=language)
    return CheckOut(
        usable=[{"provider": c.provider.name, "model": c.model.display_name, "account": c.account} for c in usable],
        skipped=[asdict(s) for s in skipped],
    )


# ------------------------------------------------------------------ test playground
def _meter(ctx: Ctx, key: str | None) -> gateway.Meter:
    ratelimit.hit(f"ai-test:{ctx.tenant.id}", get_settings().ai_tenant_test_rate_per_minute)
    billing.enforce(ctx.session, "ai")
    idem = key if key and 8 <= len(key) <= 120 else f"test-{uuid.uuid4()}"
    return gateway.Meter(
        session=ctx.session,
        tenant_id=ctx.tenant.id,
        idempotency_key=idem,
        source_type="playground",
        correlation_id=ctx.meta.correlation_id,
    )


def _unavailable(e: gateway.NoProviderAvailableError) -> ApiError:
    err = ApiError(503, "no_provider_available", str(e))
    err.detail["attempts"] = [asdict(a) for a in e.attempts]
    err.detail["skipped"] = [asdict(s) for s in e.skipped]
    return err


def _done(ctx: Ctx, kind: str, o: gateway.Outcome) -> None:
    ctx.audit(
        "ai.test_run", resource_type="ai_test", resource_id=kind, provider=o.provider, model=o.model, account=o.account
    )


def _out(o: gateway.Outcome, **kw: object) -> TestOut:
    return TestOut(
        provider=o.provider,
        model=o.model,
        account=o.account,
        attempts=[asdict(a) for a in o.attempts],
        skipped=[asdict(s) for s in o.skipped],
        units=o.units,
        **kw,
    )


@router.post("/test/chat", response_model=TestOut)
async def test_chat(
    data: ChatTestIn, ctx: Ctx = Depends(require(Perm.AI_TEST)), idempotency_key: str | None = Header(default=None)
) -> TestOut:
    m = await run_in_threadpool(_meter, ctx, idempotency_key)
    msgs = ([ChatMessage("system", data.system)] if data.system else []) + [ChatMessage("user", data.prompt)]
    outcome = gateway.Outcome("", "", "")
    try:
        text = "".join(
            [
                t
                async for t in gateway.chat_stream(  # no tools offered, so only text arrives
                    m, LLMRequest(model="", messages=msgs), language=data.language, outcome=outcome
                )
            ]
        )
    except gateway.NoProviderAvailableError as e:
        raise _unavailable(e) from None
    await run_in_threadpool(_done, ctx, "llm", outcome)
    return _out(outcome, text=text)


@router.post("/test/speech", response_model=TestOut)
async def test_speech(
    data: SpeechTestIn, ctx: Ctx = Depends(require(Perm.AI_TEST)), idempotency_key: str | None = Header(default=None)
) -> TestOut:
    m = await run_in_threadpool(_meter, ctx, idempotency_key)
    try:
        r, o = await gateway.synthesize(m, text=data.text, language=data.language, voice=data.voice)
    except gateway.NoProviderAvailableError as e:
        raise _unavailable(e) from None
    await run_in_threadpool(_done, ctx, "tts", o)
    return _out(o, audio_base64=base64.b64encode(r.audio).decode(), mime=r.mime)


@router.post("/test/transcribe", response_model=TestOut)
async def test_transcribe(
    data: TranscribeTestIn,
    ctx: Ctx = Depends(require(Perm.AI_TEST)),
    idempotency_key: str | None = Header(default=None),
) -> TestOut:
    try:
        audio = base64.b64decode(data.audio_base64, validate=True)
    except (binascii.Error, ValueError):
        raise bad_request("invalid_audio", "Audio must be base64 encoded") from None
    m = await run_in_threadpool(_meter, ctx, idempotency_key)
    try:
        r, o = await gateway.transcribe(m, audio=audio, mime=data.mime, language=data.language)
    except gateway.NoProviderAvailableError as e:
        raise _unavailable(e) from None
    await run_in_threadpool(_done, ctx, "stt", o)
    return _out(o, text=r.text)
