# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Runtime configuration. Secrets come from the environment (or a secrets manager that injects env vars)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def is_production_like(self) -> bool:
        return self.environment in ("staging", "production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production_like and settings.jwt_secret.startswith("dev-only"):
        raise RuntimeError("XV_JWT_SECRET must be set outside development")
    return settings
