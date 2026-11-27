# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Tests run against a real PostgreSQL (runtime role xplovoice_app, RLS enforced) and Redis.
Synthetic data only."""

import importlib.util
import os
import pathlib
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

os.environ.setdefault("XV_ENVIRONMENT", "test")
os.environ.setdefault("XV_WEBHOOK_DISPATCHER", "false")
os.environ.setdefault("XV_CAMPAIGN_DIALER", "false")
os.environ.setdefault("XV_BILLING_JOB", "false")
os.environ.setdefault("XV_DATABASE_URL", "postgresql+psycopg://xplovoice_app:xplovoice_app@localhost:5432/xplovoice")
os.environ.setdefault(
    "XV_MIGRATION_DATABASE_URL", "postgresql+psycopg://xplovoice_owner:xplovoice_owner@localhost:5432/xplovoice"
)
os.environ.setdefault("XV_REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("XV_JWT_SECRET", "test-secret-test-secret-test-secret-1234")

from xplovoice_api.core import ratelimit  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "seed_0002", pathlib.Path(__file__).parents[1] / "migrations/versions/0002_ai_providers.py"
)
_AI_SEED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_AI_SEED)  # type: ignore[union-attr]
from xplovoice_api.main import create_app  # noqa: E402

PASSWORD = "Str0ng-Passw0rd!"


@pytest.fixture(scope="session")
def owner_engine():
    eng = create_engine(os.environ["XV_MIGRATION_DATABASE_URL"])
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def clean(owner_engine):
    with owner_engine.begin() as c:
        c.execute(
            text(
                "truncate audit_log, refresh_tokens, invitations, tenant_memberships, tenants, users, "
                "platform_ai_routes restart identity cascade"
            )
        )
        # Restore the AI catalog to its migration seed: tests add models, prices and provider flags.
        c.execute(text("truncate ai_rate_cards, ai_models, platform_ai_routes cascade"))
        c.execute(text("truncate billing_plans, plan_prices, fx_rates, tax_rates cascade"))
        c.execute(text(_AI_SEED.MOCK_SEED))
        c.execute(
            text(
                "update ai_providers set managed_available = false, phi_eligible = false, baa_status = 'none', "
                "status = 'active', rate_limit_rpm = null"
            )
        )
    ratelimit.client().flushdb()
    yield


@pytest.fixture(scope="session")
def client():
    with TestClient(create_app()) as c:
        yield c


def register(client, *, email=None, org="Acme Clinic", country="IN"):
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": "Test User",
            "organization_name": org,
            "country_code": country,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    body["email"] = email
    return body


def auth(tokens) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}
