# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Usage metering (M15, Phase 2 scope). Records what a provider actually consumed, in the provider's units, and
prices it from the rate card in force at that moment into the provider-cost ledger. Tenant charges (plans,
markups, invoices) are a separate ledger built in Phase 7; this module never computes a customer price.

Idempotent: usage is unique per (tenant, idempotency key, unit), so a retried write is a no-op."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def record(
    session: Session,
    *,
    tenant_id: UUID,
    idempotency_key: str,
    kind: str,
    provider_id: UUID,
    model_id: UUID,
    account: str,
    credential_id: UUID | None,
    units: dict[str, Decimal | float | int],
    source_type: str,
    source_id: str | None = None,
    correlation_id: str | None = None,
    occurred_at: datetime | None = None,
    estimated: bool = False,
) -> list[int]:
    """Returns the ids of newly written usage events (empty when this key was already recorded)."""
    written: list[int] = []
    for unit, qty in units.items():
        if qty is None:
            continue
        row = session.execute(
            text(
                "insert into usage_events (tenant_id, idempotency_key, occurred_at, kind, provider_id, model_id, "
                "account, credential_id, unit, quantity, source_type, source_id, correlation_id, estimated) values "
                "(:t, :k, coalesce(:at, now()), :kind, :p, :m, :acct, :c, :unit, :q, :st, :sid, :cid, :est) "
                "on conflict (tenant_id, idempotency_key, unit) do nothing returning id, occurred_at"
            ),
            {
                "t": tenant_id,
                "k": idempotency_key,
                "at": occurred_at,
                "kind": kind,
                "p": provider_id,
                "m": model_id,
                "acct": account,
                "c": credential_id,
                "unit": unit,
                "q": Decimal(str(qty)),
                "st": source_type,
                "sid": source_id,
                "cid": correlation_id,
                "est": estimated,
            },
        ).first()
        if row is None:
            continue
        usage_id, at = row
        card = session.execute(
            text(
                "select id, unit_price, currency from ai_rate_cards where model_id = :m and unit = :u "
                "and effective_from <= :at order by effective_from desc limit 1"
            ),
            {"m": model_id, "u": unit, "at": at},
        ).first()
        amount = (card.unit_price * Decimal(str(qty))).quantize(Decimal("0.000000000001")) if card else None
        session.execute(
            text(
                "insert into provider_cost_ledger (tenant_id, usage_event_id, rate_card_id, unit_price, amount, "
                "currency, borne_by, priced) values (:t, :u, :rc, :up, :amt, :cur, :by, :priced)"
            ),
            {
                "t": tenant_id,
                "u": usage_id,
                "rc": card.id if card else None,
                "up": card.unit_price if card else None,
                "amt": amount,
                "cur": card.currency if card else None,
                "by": "customer" if account == "customer" else "platform",
                "priced": card is not None,
            },
        )
        written.append(usage_id)
    return written
