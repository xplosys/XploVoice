# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Platform administration of the AI catalog (M03 + M17): providers, models, rate cards, platform default
routes, provider health. Platform admin with an MFA session and a written reason for every change."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from ...core import audit
from ...core.config import get_settings
from ...core.context import Ctx
from ...core.errors import bad_request, not_found
from ..m17_admin.router import platform_admin
from . import breaker
from .adapters import adapter_for
from .models import Model, PlatformRoute, Provider, RateCard
from .schemas import Kind, Unit

router = APIRouter(prefix="/admin/v1/ai", tags=["admin"])


def _log(ctx: Ctx, action: str, rtype: str, rid: str, reason: str | None, **meta: object) -> None:
    audit.record(
        ctx.session,
        action=action,
        result="success",
        tenant_id=None,
        actor_user_id=ctx.user.id,
        actor_kind="platform_admin",
        resource_type=rtype,
        resource_id=rid,
        reason=reason,
        ip_hash=ctx.meta.ip_hash,
        correlation_id=ctx.meta.correlation_id,
        metadata=dict(meta),
    )


class AdminProviderOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    adapter: str
    hosting: str
    kinds: list[str]
    base_url: str | None
    regions: list[str]
    managed_available: bool
    managed_key_configured: bool
    customer_keys_allowed: bool
    phi_eligible: bool
    baa_status: str
    rate_limit_rpm: int | None
    status: str
    notes: str | None
    models: int
    health: dict


class ProviderPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(active|disabled)$")
    managed_available: bool | None = None
    customer_keys_allowed: bool | None = None
    phi_eligible: bool | None = None
    baa_status: str | None = Field(default=None, pattern="^(none|requested|signed)$")
    base_url: str | None = Field(default=None, pattern=r"^https?://\S+$", max_length=300)
    rate_limit_rpm: int | None = Field(default=None, ge=1, le=100000)
    notes: str | None = Field(default=None, max_length=1000)
    reason: str = Field(min_length=5, max_length=500)


def _provider_out(ctx: Ctx, p: Provider) -> AdminProviderOut:
    n = ctx.session.scalar(select(func.count()).select_from(Model).where(Model.provider_id == p.id)) or 0
    s = get_settings()
    configured = p.key in s.provider_keys or p.key in s.self_hosted_urls or p.hosting == "dev_only"
    return AdminProviderOut(
        id=p.id,
        key=p.key,
        name=p.name,
        adapter=p.adapter,
        hosting=p.hosting,
        kinds=p.kinds,
        base_url=p.base_url,
        regions=p.regions,
        managed_available=p.managed_available,
        managed_key_configured=configured,
        customer_keys_allowed=p.customer_keys_allowed,
        phi_eligible=p.phi_eligible,
        baa_status=p.baa_status,
        rate_limit_rpm=p.rate_limit_rpm,
        status=p.status,
        notes=p.notes,
        models=n,
        health=breaker.snapshot(p.key),
    )


@router.get("/providers", response_model=list[AdminProviderOut])
def list_providers(ctx: Ctx = Depends(platform_admin)) -> list[AdminProviderOut]:
    return [_provider_out(ctx, p) for p in ctx.session.scalars(select(Provider).order_by(Provider.name))]


@router.patch("/providers/{provider_id}", response_model=AdminProviderOut)
def update_provider(
    provider_id: uuid.UUID, data: ProviderPatch, ctx: Ctx = Depends(platform_admin)
) -> AdminProviderOut:
    p = ctx.session.get(Provider, provider_id)
    if not p:
        raise not_found()
    changes = data.model_dump(exclude_unset=True, exclude={"reason"})
    phi = changes.get("phi_eligible", p.phi_eligible)
    baa = changes.get("baa_status", p.baa_status)
    if phi and baa != "signed":
        raise bad_request("baa_required", "A provider can handle health information only with a signed BAA")
    for k, v in changes.items():
        setattr(p, k, v)
    ctx.session.flush()
    _log(ctx, "admin.ai_provider_updated", "ai_provider", str(p.id), data.reason, fields=sorted(changes))
    return _provider_out(ctx, p)


class ModelIn(BaseModel):
    provider_id: uuid.UUID
    kind: Kind
    model_key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:/@-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    languages: list[str] = Field(default_factory=list, max_length=60)
    streaming: bool = False
    function_calling: bool = False
    context_window: int | None = Field(default=None, ge=1)
    voices: list[dict] = Field(default_factory=list, max_length=200)
    reason: str = Field(min_length=5, max_length=500)


class ModelPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    languages: list[str] | None = Field(default=None, max_length=60)
    streaming: bool | None = None
    function_calling: bool | None = None
    voices: list[dict] | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, pattern="^(active|disabled)$")
    reason: str = Field(min_length=5, max_length=500)


class AdminModelOut(BaseModel):
    id: uuid.UUID
    provider_id: uuid.UUID
    kind: str
    model_key: str
    display_name: str
    languages: list[str]
    streaming: bool
    function_calling: bool
    status: str


def _model_out(m: Model) -> AdminModelOut:
    return AdminModelOut(
        id=m.id,
        provider_id=m.provider_id,
        kind=m.kind,
        model_key=m.model_key,
        display_name=m.display_name,
        languages=m.languages,
        streaming=m.streaming,
        function_calling=m.function_calling,
        status=m.status,
    )


@router.get("/models", response_model=list[AdminModelOut])
def list_models(provider_id: uuid.UUID | None = None, ctx: Ctx = Depends(platform_admin)) -> list[AdminModelOut]:
    q = select(Model).order_by(Model.kind, Model.model_key)
    if provider_id:
        q = q.where(Model.provider_id == provider_id)
    return [_model_out(m) for m in ctx.session.scalars(q)]


@router.post("/models", response_model=AdminModelOut, status_code=201)
def add_model(data: ModelIn, ctx: Ctx = Depends(platform_admin)) -> AdminModelOut:
    p = ctx.session.get(Provider, data.provider_id)
    if not p or data.kind not in p.kinds or adapter_for(p.adapter, data.kind) is None:
        raise bad_request("kind_not_supported", "This provider has no adapter for that kind of model")
    if ctx.session.scalar(
        select(Model.id).where(Model.provider_id == p.id, Model.kind == data.kind, Model.model_key == data.model_key)
    ):
        raise bad_request("model_exists", "That model is already in the catalog")
    m = Model(**data.model_dump(exclude={"reason"}))
    ctx.session.add(m)
    ctx.session.flush()
    ctx.session.refresh(m)
    _log(ctx, "admin.ai_model_added", "ai_model", str(m.id), data.reason, provider=p.key, model=m.model_key)
    return _model_out(m)


@router.patch("/models/{model_id}", response_model=AdminModelOut)
def update_model(model_id: uuid.UUID, data: ModelPatch, ctx: Ctx = Depends(platform_admin)) -> AdminModelOut:
    m = ctx.session.get(Model, model_id)
    if not m:
        raise not_found()
    changes = data.model_dump(exclude_unset=True, exclude={"reason"})
    for k, v in changes.items():
        setattr(m, k, v)
    ctx.session.flush()
    _log(ctx, "admin.ai_model_updated", "ai_model", str(m.id), data.reason, fields=sorted(changes))
    return _model_out(m)


class RateCardIn(BaseModel):
    model_id: uuid.UUID
    unit: Unit
    unit_price: Decimal = Field(ge=0, max_digits=24, decimal_places=12)
    currency: str = Field(pattern="^(USD|INR)$")
    effective_from: datetime | None = None
    source: str = Field(min_length=5, max_length=300, description="Where the price came from, e.g. a dated price list")
    reason: str = Field(min_length=5, max_length=500)


class RateCardOut(BaseModel):
    id: uuid.UUID
    model_id: uuid.UUID
    unit: str
    unit_price: Decimal
    currency: str
    effective_from: datetime
    source: str


@router.get("/rate-cards", response_model=list[RateCardOut])
def list_rate_cards(model_id: uuid.UUID, ctx: Ctx = Depends(platform_admin)) -> list[RateCardOut]:
    cards = ctx.session.scalars(
        select(RateCard).where(RateCard.model_id == model_id).order_by(RateCard.unit, RateCard.effective_from.desc())
    )
    return [
        RateCardOut(
            id=c.id,
            model_id=c.model_id,
            unit=c.unit,
            unit_price=c.unit_price,
            currency=c.currency,
            effective_from=c.effective_from,
            source=c.source,
        )
        for c in cards
    ]


@router.post("/rate-cards", response_model=RateCardOut, status_code=201)
def add_rate_card(data: RateCardIn, ctx: Ctx = Depends(platform_admin)) -> RateCardOut:
    if not ctx.session.get(Model, data.model_id):
        raise not_found()
    c = RateCard(
        model_id=data.model_id,
        unit=data.unit,
        unit_price=data.unit_price,
        currency=data.currency,
        effective_from=data.effective_from or datetime.now(UTC),
        source=data.source,
        created_by=ctx.user.id,
    )
    ctx.session.add(c)
    ctx.session.flush()
    _log(ctx, "admin.ai_rate_card_added", "ai_rate_card", str(c.id), data.reason, unit=c.unit, currency=c.currency)
    return RateCardOut(
        id=c.id,
        model_id=c.model_id,
        unit=c.unit,
        unit_price=c.unit_price,
        currency=c.currency,
        effective_from=c.effective_from,
        source=c.source,
    )


class PlatformRoutesIn(BaseModel):
    model_ids: list[uuid.UUID] = Field(max_length=5)
    reason: str = Field(min_length=5, max_length=500)


@router.get("/routes")
def get_platform_routes(ctx: Ctx = Depends(platform_admin)) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {"llm": [], "stt": [], "tts": []}
    for r in ctx.session.scalars(select(PlatformRoute).order_by(PlatformRoute.kind, PlatformRoute.priority)):
        m = ctx.session.get(Model, r.model_id)
        out[r.kind].append({"priority": r.priority, "model_id": str(m.id), "model": m.display_name})
    return out


@router.put("/routes/{kind}")
def set_platform_routes(kind: Kind, data: PlatformRoutesIn, ctx: Ctx = Depends(platform_admin)) -> dict:
    for mid in data.model_ids:
        m = ctx.session.get(Model, mid)
        if not m or m.kind != kind:
            raise bad_request("invalid_model", f"Choose {kind} models only")
    ctx.session.execute(delete(PlatformRoute).where(PlatformRoute.kind == kind))
    for i, mid in enumerate(data.model_ids, start=1):
        ctx.session.add(PlatformRoute(kind=kind, priority=i, model_id=mid))
    ctx.session.flush()
    _log(ctx, "admin.ai_platform_routes_updated", "ai_routes", kind, data.reason, count=len(data.model_ids))
    return get_platform_routes(ctx)
