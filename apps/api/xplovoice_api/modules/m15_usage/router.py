# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Usage reporting (M15, Phase 2 scope): quantities in provider units and provider cost. Tenant charges, plans
and invoices are Phase 7."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text

from ...core.context import Ctx, require
from ...core.permissions import Perm

router = APIRouter(prefix="/v1/usage", tags=["usage"])


class UsageRow(BaseModel):
    day: str
    kind: str
    provider: str
    model: str
    account: str
    unit: str
    quantity: Decimal
    cost: Decimal | None
    currency: str | None
    unpriced_events: int


class UsageEvent(BaseModel):
    id: int
    occurred_at: datetime
    kind: str
    provider: str
    model: str
    account: str
    unit: str
    quantity: Decimal
    source_type: str
    cost: Decimal | None
    currency: str | None
    borne_by: str | None


@router.get("/summary", response_model=list[UsageRow])
def summary(ctx: Ctx = Depends(require(Perm.USAGE_READ)), days: int = Query(30, ge=1, le=366)) -> list[UsageRow]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        ctx.session.execute(
            text(
                "select to_char(timezone(:tz, u.occurred_at), 'YYYY-MM-DD') as day, u.kind, p.name as provider, "
                "m.display_name as model, u.account, u.unit, sum(u.quantity) as quantity, sum(c.amount) as cost, "
                "min(c.currency) as currency, count(*) filter (where not c.priced) as unpriced_events "
                "from usage_events u join ai_providers p on p.id = u.provider_id join ai_models m on m.id = u.model_id "
                "left join provider_cost_ledger c on c.usage_event_id = u.id "
                "where u.tenant_id = app_tenant_id() and u.occurred_at >= :since "
                "group by 1, 2, 3, 4, 5, 6 order by 1 desc, 2, 3, 4, 6"
            ),
            {"tz": ctx.tenant.timezone, "since": since},
        )
        .mappings()
        .all()
    )
    return [UsageRow(**r) for r in rows]


@router.get("/events", response_model=list[UsageEvent])
def events(
    ctx: Ctx = Depends(require(Perm.USAGE_READ)), limit: int = Query(50, ge=1, le=200), before_id: int | None = None
) -> list[UsageEvent]:
    rows = (
        ctx.session.execute(
            text(
                "select u.id, u.occurred_at, u.kind, p.name as provider, m.display_name as model, u.account, u.unit, "
                "u.quantity, u.source_type, c.amount as cost, c.currency, c.borne_by "
                "from usage_events u join ai_providers p on p.id = u.provider_id join ai_models m on m.id = u.model_id "
                "left join provider_cost_ledger c on c.usage_event_id = u.id "
                "where u.tenant_id = app_tenant_id() and (cast(:before as bigint) is null or u.id < :before) "
                "order by u.id desc limit :limit"
            ),
            {"before": before_id, "limit": limit},
        )
        .mappings()
        .all()
    )
    return [UsageEvent(**r) for r in rows]
