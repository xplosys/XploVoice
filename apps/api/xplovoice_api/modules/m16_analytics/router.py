# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Analytics and reporting (M16, Phase 7): call volumes, outcomes, durations, containment, agents, channels and
what the agents did (appointments, leads, tickets, tool runs), plus charges per day, for one organisation.

Read-only over the operational tables, inside the tenant's RLS context, grouped by day in the organisation's time
zone. Counts and durations only: no transcripts or caller numbers leave this endpoint."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text

from ...core.context import Ctx, require
from ...core.permissions import Perm, has

router = APIRouter(prefix="/v1/analytics", tags=["M16 analytics"])

DONE = ("completed",)
FAILED = ("failed", "busy", "no_answer", "cancelled", "disconnected")


class Totals(BaseModel):
    calls: int
    completed: int
    failed: int
    in_progress: int
    talk_minutes: Decimal
    average_seconds: Decimal | None
    transferred: int
    escalated: int
    contained_percent: Decimal | None  # completed calls the agent handled to the end, without a person


class DayRow(BaseModel):
    day: str
    calls: int
    completed: int
    failed: int
    talk_minutes: Decimal
    charges: Decimal | None


class AgentRow(BaseModel):
    agent_id: str
    agent: str
    calls: int
    completed: int
    average_seconds: Decimal | None
    transferred: int


class Count(BaseModel):
    key: str
    count: int


class Outcomes(BaseModel):
    appointments_booked: int
    leads_created: int
    tickets_created: int
    tool_runs: int
    tool_failures: int
    opt_outs: int


class AnalyticsOut(BaseModel):
    days: int
    timezone: str
    currency: str
    totals: Totals
    by_day: list[DayRow]
    by_agent: list[AgentRow]
    by_channel: list[Count]
    end_reasons: list[Count]
    outcomes: Outcomes


@router.get("/overview", response_model=AnalyticsOut)
def overview(ctx: Ctx = Depends(require(Perm.ANALYTICS_READ)), days: int = Query(30, ge=1, le=366)) -> AnalyticsOut:
    s = ctx.session
    tz = ctx.tenant.timezone
    since = datetime.now(UTC) - timedelta(days=days)
    p = {"since": since, "tz": tz}
    t = s.execute(
        text(
            "select count(*) as calls, count(*) filter (where c.state = 'completed') as completed, "
            "count(*) filter (where c.state in ('failed', 'busy', 'no_answer', 'cancelled', 'disconnected')) "
            "as failed, "
            "count(*) filter (where c.ended_at is null) as in_progress, "
            "coalesce(sum(c.duration_seconds), 0) / 60 as talk_minutes, avg(c.duration_seconds) as average_seconds, "
            "count(*) filter (where c.end_reason = 'transferred') as transferred, "
            "count(*) filter (where c.end_reason = 'escalated') as escalated, "
            "count(*) filter (where c.state = 'completed' and coalesce(c.end_reason, '') not in "
            "('transferred', 'escalated')) as contained "
            "from calls c where c.tenant_id = app_tenant_id() and c.created_at >= :since "
            "and c.channel <> 'chat'"
        ),
        p,
    ).one()
    totals = Totals(
        calls=t.calls,
        completed=t.completed,
        failed=t.failed,
        in_progress=t.in_progress,
        talk_minutes=Decimal(t.talk_minutes).quantize(Decimal("0.01")),
        average_seconds=Decimal(t.average_seconds).quantize(Decimal("0.1")) if t.average_seconds is not None else None,
        transferred=t.transferred,
        escalated=t.escalated,
        contained_percent=(Decimal(t.contained * 100) / t.completed).quantize(Decimal("0.1")) if t.completed else None,
    )
    show_money = has(ctx.membership.role, Perm.BILLING_READ)
    charges: dict[str, Decimal] = {}
    if show_money:
        charges = {
            r.day: r.amount
            for r in s.execute(
                text(
                    "select to_char(timezone(:tz, occurred_at), 'YYYY-MM-DD') as day, sum(amount) as amount "
                    "from charge_ledger where tenant_id = app_tenant_id() and occurred_at >= :since group by 1"
                ),
                p,
            ).all()
        }
    by_day = [
        DayRow(
            day=r.day,
            calls=r.calls,
            completed=r.completed,
            failed=r.failed,
            talk_minutes=Decimal(r.minutes).quantize(Decimal("0.01")),
            charges=charges.get(r.day, Decimal(0)) if show_money else None,
        )
        for r in s.execute(
            text(
                "select to_char(timezone(:tz, c.created_at), 'YYYY-MM-DD') as day, count(*) as calls, "
                "count(*) filter (where c.state = 'completed') as completed, "
                "count(*) filter (where c.state in ('failed', 'busy', 'no_answer', 'cancelled', 'disconnected')) "
                "as failed, coalesce(sum(c.duration_seconds), 0) / 60 as minutes "
                "from calls c where c.tenant_id = app_tenant_id() and c.created_at >= :since "
                "and c.channel <> 'chat'"
                " group by 1 order by 1"
            ),
            p,
        ).all()
    ]
    by_agent = [
        AgentRow(
            agent_id=str(r.agent_id),
            agent=r.name,
            calls=r.calls,
            completed=r.completed,
            average_seconds=Decimal(r.avg).quantize(Decimal("0.1")) if r.avg is not None else None,
            transferred=r.transferred,
        )
        for r in s.execute(
            text(
                "select c.agent_id, a.name, count(*) as calls, count(*) filter (where c.state = 'completed') as "
                "completed, avg(c.duration_seconds) as avg, count(*) filter (where c.end_reason = 'transferred') "
                "as transferred from calls c join agents a on a.id = c.agent_id where c.tenant_id = app_tenant_id() "
                "and c.created_at >= :since and c.channel <> 'chat' group by 1, 2 order by 3 desc limit 50"
            ),
            p,
        ).all()
    ]

    def counts(sql: str) -> list[Count]:
        return [Count(key=r.k or "unknown", count=r.n) for r in s.execute(text(sql), p).all()]

    by_channel = counts(
        "select c.channel || ':' || c.direction as k, count(*) as n "
        "from calls c where c.tenant_id = app_tenant_id() and c.created_at >= :since "
        "and c.channel <> 'chat'"
        " group by 1 order by 2 desc"
    )
    end_reasons = counts(
        "select c.end_reason as k, count(*) as n "
        "from calls c where c.tenant_id = app_tenant_id() and c.created_at >= :since "
        "and c.channel <> 'chat'"
        " and c.ended_at is not null group by 1 order by 2 desc"
    )

    def n(sql: str) -> int:
        return int(s.scalar(text(sql), p) or 0)

    outcomes = Outcomes(
        appointments_booked=n(
            "select count(*) from appointments where tenant_id = app_tenant_id() and created_at >= :since"
        ),
        leads_created=n("select count(*) from leads where tenant_id = app_tenant_id() and created_at >= :since"),
        tickets_created=n("select count(*) from tickets where tenant_id = app_tenant_id() and created_at >= :since"),
        tool_runs=n("select count(*) from tool_executions where tenant_id = app_tenant_id() and created_at >= :since"),
        tool_failures=n(
            "select count(*) from tool_executions where tenant_id = app_tenant_id() "
            "and created_at >= :since and status in ('failed', 'timed_out')"
        ),
        opt_outs=n(
            "select count(*) from suppression_entries where tenant_id = app_tenant_id() "
            "and created_at >= :since and reason = 'opt_out'"
        ),
    )
    return AnalyticsOut(
        days=days,
        timezone=tz,
        currency=ctx.tenant.currency,
        totals=totals,
        by_day=by_day,
        by_agent=by_agent,
        by_channel=by_channel,
        end_reasons=end_reasons,
        outcomes=outcomes,
    )
