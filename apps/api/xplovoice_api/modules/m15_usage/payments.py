# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Payment-provider adapters (M15, Phase 7).

No payment gateway is contracted yet, so only the test provider exists. It is development and test only (refused
in staging and production, like the mock AI provider and the simulated carrier) and never moves money: it settles
a payment by sending its own signed webhook through the same verified, deduplicated path a real gateway's
webhooks will use. Card numbers and other payment details are never sent to or stored by XploVoice."""

import hashlib
import hmac
import json
import secrets
import time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text

from ...core import audit
from ...core.config import get_settings
from ...core.db import session_scope
from ..m13_integrations.events import emit
from . import billing

TEST_OUTCOMES = ("succeed", "decline")


class PaymentError(Exception):
    pass


def test_allowed() -> None:
    if get_settings().is_production_like:
        raise PaymentError("The test payment provider is for development and tests only.")


def new_ref() -> str:
    return f"testpay_{secrets.token_urlsafe(18)}"


def sign(body: bytes, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    mac = hmac.new(get_settings().test_payment_secret.encode(), f"{ts}.".encode() + body, hashlib.sha256)
    return f"t={ts},v1={mac.hexdigest()}"


def verify(body: bytes, header: str | None) -> bool:
    if not header:
        return False
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs(time.time() - ts) > get_settings().carrier_webhook_tolerance_seconds:
        return False
    mac = hmac.new(get_settings().test_payment_secret.encode(), f"{ts}.".encode() + body, hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), parts.get("v1", ""))


def test_settlement(ref: str, amount: Decimal, currency: str, outcome: str) -> tuple[bytes, str]:
    """The webhook the test provider sends once it has 'processed' a payment."""
    body = json.dumps(
        {
            "id": f"evt_{secrets.token_hex(12)}",
            "type": "payment.succeeded" if outcome == "succeed" else "payment.failed",
            "payment_ref": ref,
            "amount": str(amount),
            "currency": currency,
            "failure_reason": None if outcome == "succeed" else "Card declined (test provider)",
        }
    ).encode()
    return body, sign(body)


def handle_event(provider: str, event: dict) -> str:
    """Applies one verified provider event. Returns what happened: applied, duplicate, ignored or unknown."""
    with session_scope() as s:
        row = s.execute(
            text("select tenant_id, payment_id from find_payment_by_ref(:p, :r)"),
            {"p": provider, "r": str(event.get("payment_ref", ""))},
        ).first()
    if row is None:
        return "unknown"
    tenant_id, payment_id = row
    with session_scope(tenant_id=tenant_id) as s:
        stored = s.execute(
            text(
                "insert into payment_events (tenant_id, provider_key, event_id, payment_id, type) values "
                "(app_tenant_id(), :p, :e, :pid, :t) on conflict (provider_key, event_id) do nothing returning id"
            ),
            {"p": provider, "e": str(event.get("id", ""))[:120], "pid": payment_id, "t": str(event.get("type"))[:60]},
        ).first()
        if stored is None:
            return "duplicate"
        pay = s.execute(text("select * from payments where id = :i"), {"i": payment_id}).mappings().first()
        assert pay is not None
        if pay["status"] != "pending":
            return "ignored"  # a later event never overturns a settled payment
        etype = event.get("type")
        try:
            amount = Decimal(str(event.get("amount")))
        except ArithmeticError:
            amount = Decimal(-1)
        if etype == "payment.succeeded" and (amount != pay["amount"] or event.get("currency") != pay["currency"]):
            etype, event = "payment.failed", {**event, "failure_reason": "Amount or currency did not match"}
        if etype == "payment.succeeded":
            s.execute(
                text("update payments set status = 'succeeded', completed_at = now() where id = :i"), {"i": payment_id}
            )
            billing.mark_paid(s, pay["invoice_id"], pay["amount"])
            inv = s.execute(text("select number, status from invoices where id = :i"), {"i": pay["invoice_id"]}).first()
            if inv and inv.status == "paid":
                emit(s, tenant_id, "invoice.paid", {"invoice_id": str(pay["invoice_id"]), "number": inv.number})
        elif etype == "payment.failed":
            s.execute(
                text("update payments set status = 'failed', failure_reason = :r, completed_at = now() where id = :i"),
                {"i": payment_id, "r": str(event.get("failure_reason") or "Payment failed")[:200]},
            )
        else:
            return "ignored"
        s.execute(text("update payment_events set applied = true where id = :i"), {"i": stored.id})
        audit.record(
            s,
            action=f"payment.{'succeeded' if etype == 'payment.succeeded' else 'failed'}",
            result="success",
            tenant_id=tenant_id,
            actor_kind="service",
            resource_type="payment",
            resource_id=str(payment_id),
            metadata={"provider": provider, "invoice_id": str(pay["invoice_id"])},
        )
        return "applied"


def payment_for(s, payment_id: UUID):  # type: ignore[no-untyped-def]
    return s.execute(text("select * from payments where id = :i"), {"i": payment_id}).mappings().first()
