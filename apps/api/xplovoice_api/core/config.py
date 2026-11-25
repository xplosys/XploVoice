# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Runtime configuration. Secrets come from the environment (or a secrets manager that injects env vars)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_LIVEKIT_SECRET = "dev-only-livekit-secret-change-me-0123456789"  # noqa: S105 - refused in production


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="XV_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "staging", "production"] = "development"

    # Runtime role: must NOT be superuser or BYPASSRLS (LLD v1.3 section 4).
    database_url: str = "postgresql+psycopg://xplovoice_app:xplovoice_app@localhost:5432/xplovoice"
    # Migration/owner role, used only by Alembic.
    migration_database_url: str = "postgresql+psycopg://xplovoice_owner:xplovoice_owner@localhost:5432/xplovoice"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = Field(default="dev-only-change-me-dev-only-change-me", min_length=32)
    jwt_issuer: str = "https://api.xplovoice.com"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    mfa_issuer: str = "XploVoice"

    cors_origins: list[str] = ["http://localhost:3000"]
    login_rate_limit_per_minute: int = 10

    # Data encryption keys (Fernet, url-safe base64, 32 bytes). The first encrypts; all decrypt, so keys can be
    # rotated by prepending a new one. Required outside development/test.
    encryption_keys: list[str] = []

    # M03: XploVoice-managed provider accounts, keyed by provider key, e.g. {"openai": "sk-..."}. Injected from
    # the secrets manager. A provider without a key here is "awaiting configuration" for managed use.
    provider_keys: dict[str, str] = {}
    # Endpoints of self-hosted model servers, keyed by provider key, e.g. {"ollama": "http://ollama:11434/v1"}.
    self_hosted_urls: dict[str, str] = {}
    ai_request_timeout_seconds: float = 30.0
    ai_tenant_test_rate_per_minute: int = 20
    breaker_failure_threshold: int = 5
    breaker_open_seconds: int = 30

    # Phase 3 voice. LiveKit (self-hosted in development; ADR-0006). `livekit_url` is what browsers connect to,
    # `livekit_internal_url` what voice workers use. The dev key pair matches infra/compose/livekit.yaml.
    livekit_url: str = "ws://localhost:7880"
    livekit_internal_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = Field(default=DEV_LIVEKIT_SECRET, min_length=32)
    # Shared secret that voice workers present on /internal/v1, in addition to a per-call token.
    worker_key: str = Field(default="dev-only-worker-key", min_length=16)
    voice_token_minutes: int = 10  # browser LiveKit tokens: enough to join, never the whole call
    max_concurrent_calls_per_tenant: int = 2
    max_call_seconds: int = 900  # hard platform ceiling; agents can set less

    # Phase 5. ClamAV daemon for knowledge-base uploads, e.g. "tcp://clamav:3310". Without it, staging and
    # production refuse uploads; development and test use a built-in check that is not a malware scanner.
    clamav_url: str | None = None
    tool_timeout_seconds: float = 8.0
    # Outbound webhooks (M13): the in-process dispatcher. Off in tests, which drive it directly.
    webhook_dispatcher: bool = True
    webhook_timeout_seconds: float = 10.0

    @property
    def is_production_like(self) -> bool:
        return self.environment in ("staging", "production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production_like and settings.jwt_secret.startswith("dev-only"):
        raise RuntimeError("XV_JWT_SECRET must be set outside development")
    if settings.is_production_like and (
        settings.worker_key.startswith("dev-only") or settings.livekit_api_secret == DEV_LIVEKIT_SECRET
    ):
        raise RuntimeError("XV_WORKER_KEY and XV_LIVEKIT_API_SECRET must be set outside development")
    if settings.is_production_like and not settings.encryption_keys:
        raise RuntimeError("XV_ENCRYPTION_KEYS must be set outside development")
    return settings
