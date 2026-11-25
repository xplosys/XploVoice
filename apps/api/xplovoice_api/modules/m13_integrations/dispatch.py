# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Outbound webhook delivery (M13). Each delivery is signed with the endpoint's own secret
(X-XploVoice-Signature: t=<unix>,v1=<hex HMAC-SHA256 of "<t>.<body>">), carries an idempotency key
(X-XploVoice-Delivery) so a receiver can drop repeats, and is retried with exponential backoff up to 8 attempts,
then marked dead.

Requests go only to the HTTPS URL an admin registered, after checking that it resolves to public addresses:
never to private, loopback, link-local or metadata addresses (SSRF). Redirects are not followed."""

import asyncio
import contextlib
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

import httpx
from prometheus_client import Counter
from sqlalchemy import select, text

from ...core.config import get_settings
from ...core.db import session_scope
from ...core.security import decrypt_secret
from .models import Integration, IntegrationEvent, WebhookDelivery

log = logging.getLogger("xplovoice.webhooks")
DELIVERIES = Counter("xv_webhook_deliveries_total", "Webhook delivery attempts", ["outcome"])
MAX_ATTEMPTS = 8

_transport: httpx.AsyncBaseTransport | None = None  # tests swap this


class UnsafeUrlError(ValueError):
    pass


def resolve(host: str) -> list[str]:
    return [i[4][0] for i in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)]


def check_url(url: str, *, resolve_host: bool = True) -> str:
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise UnsafeUrlError("Webhook URLs must be https:// with a host name and no credentials.")
    if u.port not in (None, 443, 8443):
        raise UnsafeUrlError("Webhook URLs must use port 443 or 8443.")
    host = u.hostname
    try:
        ips = [host] if _is_ip(host) else (resolve(host) if resolve_host else [])
    except OSError:
        raise UnsafeUrlError("That host name doesn't resolve.") from None
    for ip in ips:
        a = ipaddress.ip_address(ip)
        if not a.is_global or a.is_multicast:
            raise UnsafeUrlError("Webhook URLs must point to a public internet address.")
    return url


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def sign(secret: str, ts: int, body: bytes) -> str:
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(3600, 30 * 2 ** (attempts - 1)))


async def deliver(delivery_id: int, tenant_id: UUID) -> str:
    """One attempt for one delivery, under the delivery's own tenant context."""

    def load() -> tuple[WebhookDelivery, Integration, IntegrationEvent] | None:
        with session_scope(tenant_id=tenant_id) as s:
            d = s.scalar(
                select(WebhookDelivery).where(WebhookDelivery.id == delivery_id).with_for_update(skip_locked=True)
            )
            if not d or d.status not in ("pending", "retrying"):
                return None
            h = s.get(Integration, d.integration_id)
            ev = s.get(IntegrationEvent, d.event_id)
            assert h and ev
            d.attempts += 1
            d.next_attempt_at = datetime.now(UTC) + _backoff(d.attempts)  # claim it: others skip until then
            s.flush()
            s.expunge_all()
            return d, h, ev

    from starlette.concurrency import run_in_threadpool

    got = await run_in_threadpool(load)
    if got is None:
        return "skipped"
    d, h, ev = got
    outcome, code, err = "failed", None, None
    if h.status != "active":
        outcome, err = "dead", "The webhook is disabled."
    else:
        body = json.dumps(
            {"id": f"evt_{ev.id}", "type": ev.type, "created_at": ev.created_at.isoformat(), "data": ev.payload},
            separators=(",", ":"),
        ).encode()
        ts = int(time.time())
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "XploVoice-Webhooks/1",
            "X-XploVoice-Event": ev.type,
            "X-XploVoice-Delivery": f"dlv_{d.id}",
            "X-XploVoice-Signature": sign(decrypt_secret(h.secret_ciphertext or ""), ts, body),
        }
        try:
            url = await run_in_threadpool(check_url, h.settings.get("url", ""))
            async with httpx.AsyncClient(
                transport=_transport, timeout=get_settings().webhook_timeout_seconds, follow_redirects=False
            ) as c:
                r = await c.post(url, content=body, headers=headers)
            code = r.status_code
            outcome = "succeeded" if 200 <= code < 300 else "failed"
            err = None if outcome == "succeeded" else f"HTTP {code}"
        except UnsafeUrlError as e:
            outcome, err = "dead", str(e)
        except httpx.HTTPError as e:
            err = f"Connection failed ({type(e).__name__})"

    def save() -> None:
        with session_scope(tenant_id=tenant_id) as s:
            row = s.get(WebhookDelivery, d.id)
            assert row is not None
            row.last_status, row.last_error = code, err
            if outcome == "succeeded":
                row.status = "succeeded"
            elif outcome == "dead" or row.attempts >= MAX_ATTEMPTS:
                row.status = "dead"
            else:
                row.status = "retrying"

    await run_in_threadpool(save)
    DELIVERIES.labels(outcome).inc()
    return outcome


async def run_due(limit: int = 20) -> int:
    def due() -> list[tuple[int, UUID]]:
        with session_scope() as s:
            return [
                (r[0], r[1])
                for r in s.execute(text("select id, tenant_id from due_webhook_deliveries(:n)"), {"n": limit})
            ]

    from starlette.concurrency import run_in_threadpool

    rows = await run_in_threadpool(due)
    for did, tid in rows:
        try:
            await deliver(did, tid)
        except Exception:  # noqa: BLE001 - one bad delivery must not stop the others
            log.exception("webhook delivery %s failed", did)
    return len(rows)


async def loop(interval: float = 5.0) -> None:
    """Runs inside each API process. Deliveries are claimed with SKIP LOCKED, so several processes can run it."""
    while True:
        with contextlib.suppress(Exception):
            await run_due()
        await asyncio.sleep(interval)
