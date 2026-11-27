# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import datetime
from typing import Literal
from uuid import UUID

import phonenumbers
from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator

InviteRole = Literal["admin", "agent_designer", "operator", "viewer", "privacy_officer"]
AnyRole = Literal["owner", "admin", "agent_designer", "operator", "viewer", "privacy_officer"]


class TenantOut(BaseModel):
    id: UUID
    name: str
    slug: str
    country_code: str
    timezone: str
    currency: str
    default_language: str
    date_format: str
    business_phone: str | None
    industry: str | None
    website: str | None
    status: str
    created_at: datetime


class TenantPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    timezone: str | None = None
    default_language: str | None = None
    business_phone: str | None = None
    industry: str | None = Field(default=None, max_length=80)
    website: HttpUrl | None = None

    @field_validator("business_phone")
    @classmethod
    def e164(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            n = phonenumbers.parse(v, None)
        except phonenumbers.NumberParseException:
            raise ValueError("Use international format with the country code, for example +14155550100") from None
        if not phonenumbers.is_valid_number(n):
            raise ValueError("Not a valid phone number")
        return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)


class MyTenantOut(BaseModel):
    tenant_id: UUID
    name: str
    role: str
    current: bool


class MemberOut(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    display_name: str
    role: str
    mfa_enabled: bool
    created_at: datetime


class MemberPatch(BaseModel):
    role: AnyRole


class InviteIn(BaseModel):
    email: EmailStr
    role: InviteRole


class InviteOut(BaseModel):
    id: UUID
    email: str
    role: str
    expires_at: datetime
    accept_url: str | None = Field(
        default=None, description="Returned only while email delivery is awaiting configuration"
    )


class InvitationOut(BaseModel):
    id: UUID
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None


class AcceptInviteIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class AuditOut(BaseModel):
    id: int
    created_at: datetime
    actor_user_id: UUID | None
    actor_kind: str
    action: str
    resource_type: str | None
    resource_id: str | None
    result: str
    correlation_id: str | None


class LanguageOut(BaseModel):
    code: str
    name: str


class CountryOut(BaseModel):
    code: str
    name: str
    currency: str
    default_timezone: str
    timezones: list[str]
    languages: list[LanguageOut]
    date_format: str
