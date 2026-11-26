# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""XploVoice control-plane API (FastAPI modular monolith)."""

import asyncio
import contextlib
import re
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import Counter, Histogram

from .core.config import get_settings
from .modules.m01_identity.router import router as identity_router
from .modules.m02_tenant.router import router as tenant_router
from .modules.m03_ai.admin import router as ai_admin_router
from .modules.m03_ai.router import router as ai_router
from .modules.m04_telephony.router import router as telephony_router
from .modules.m04_telephony.webhooks import router as carrier_webhooks_router
from .modules.m05_agents.router import router as agents_router
from .modules.m07_campaigns import dialer
from .modules.m07_campaigns.router import router as campaigns_router
from .modules.m08_calls.internal import router as worker_router
from .modules.m08_calls.router import router as calls_router
from .modules.m09_tools.router import router as tools_router
from .modules.m11_workflows.router import router as workflows_router
from .modules.m12_knowledge.router import router as knowledge_router
from .modules.m13_integrations import dispatch as webhooks
from .modules.m13_integrations.router import router as integrations_router
from .modules.m14_support.router import router as support_router
from .modules.m15_usage.router import router as usage_router
from .modules.m17_admin.router import router as admin_router
from .modules.m18_ops.router import router as ops_router
from .modules.m22_consent.router import router as consent_router

REQUESTS = Counter("xv_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("xv_http_request_seconds", "HTTP latency", ["method", "route"])
_CID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    tasks = []
    if settings.webhook_dispatcher:
        tasks.append(asyncio.create_task(webhooks.loop()))
    if settings.campaign_dialer:  # outbound campaigns and the inbound queue (safe in several processes)
        tasks.append(asyncio.create_task(dialer.loop()))
    yield
    for task in tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        lifespan=lifespan,
        title="XploVoice API",
        version="0.1.0",
        description="XploVoice control-plane API. Copyright (c) 2026 Xplosys. All rights reserved. "
        "Confidential - Proprietary to Xplosys.",
        docs_url=None if settings.environment == "production" else "/docs",
        openapi_url=None if settings.environment == "production" else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],  # never X-Worker-Key
    )

    @app.middleware("http")
    async def correlation_and_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        incoming = request.headers.get("x-request-id", "")
        cid = incoming if _CID.match(incoming) else str(uuid.uuid4())
        request.state.correlation_id = cid
        start = time.perf_counter()
        response = await call_next(request)
        route = getattr(request.scope.get("route"), "path", "unmatched")
        LATENCY.labels(request.method, route).observe(time.perf_counter() - start)
        REQUESTS.labels(request.method, route, str(response.status_code)).inc()
        response.headers["X-Request-ID"] = cid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if not request.url.path.startswith(("/docs", "/redoc")):  # API docs load their own assets (dev only)
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
            response.headers["Cache-Control"] = "no-store"
        if settings.is_production_like:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        return response

    for r in (
        ops_router,
        identity_router,
        tenant_router,
        ai_router,
        usage_router,
        agents_router,
        calls_router,
        worker_router,
        knowledge_router,
        tools_router,
        workflows_router,
        support_router,
        integrations_router,
        admin_router,
        ai_admin_router,
        telephony_router,
        carrier_webhooks_router,
        campaigns_router,
        consent_router,
    ):
        app.include_router(r)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz,metrics")
    return app


app = create_app()
