# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from ...core import ratelimit
from ...core.db import get_engine

router = APIRouter(tags=["M18 Observability & Operations"])


@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(response: Response) -> dict:
    checks = {}
    try:
        with get_engine().connect() as c:
            c.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001
        checks["database"] = "error"
    try:
        ratelimit.client().ping()
        checks["redis"] = "ok"
    except Exception:  # noqa: BLE001
        checks["redis"] = "error"
    ok = all(v == "ok" for v in checks.values())
    response.status_code = 200 if ok else 503
    return {"status": "ok" if ok else "degraded", "checks": checks}


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    # Exposed on the internal network only (reverse proxy blocks /metrics publicly). No tenant or PII labels.
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
