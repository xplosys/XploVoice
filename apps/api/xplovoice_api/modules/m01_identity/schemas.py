# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


def _strong(pw: str) -> str:
    if len(pw) < 12:
        raise ValueError("Password must be at least 12 characters")
    classes = sum(
        [
            any(c.islower() for c in pw),
            any(c.isupper() for c in pw),
            any(c.isdigit() for c in pw),
            any(not c.isalnum() for c in pw),
        ]
    )
    if classes < 3:
        raise ValueError("Use at least three of: lowercase, uppercase, digits, symbols")
    return pw


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)
    display_name: str = Field(min_length=1, max_length=120)
    organization_name: str = Field(min_length=1, max_length=160)
    country_code: Literal["IN", "US"]
    timezone: str | None = None

    _pw = field_validator("password")(_strong)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)
    mfa_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    tenant_id: UUID | None = None


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class SwitchTenantIn(BaseModel):
    tenant_id: UUID


class TokenOut(BaseModel):
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    tenant_id: UUID


class MeOut(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    email_verified: bool
    mfa_enabled: bool
    is_platform_admin: bool
    tenant_id: UUID
    tenant_name: str
    role: str
    permissions: list[str]


class MfaEnrollOut(BaseModel):
    secret: str
    otpauth_uri: str


class MfaCodeIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class MfaDisableIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    password: str = Field(max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)

    _pw = field_validator("new_password")(_strong)
