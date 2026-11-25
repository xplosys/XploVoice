# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Kind = Literal["llm", "stt", "tts"]
Unit = Literal["input_token", "output_token", "audio_second", "character", "request"]


class PriceOut(BaseModel):
    unit: str
    unit_price: Decimal
    currency: str
    effective_from: datetime
    source: str


class ModelOut(BaseModel):
    id: UUID
    kind: str
    model_key: str
    display_name: str
    languages: list[str]
    streaming: bool
    function_calling: bool
    context_window: int | None
    voices: list
    status: str
    prices: list[PriceOut] = []


class ProviderOut(BaseModel):
    id: UUID
    key: str
    name: str
    hosting: str
    kinds: list[str]
    regions: list[str]
    phi_eligible: bool
    customer_keys_allowed: bool
    managed_status: str  # available | awaiting configuration | development only
    status: str
    models: list[ModelOut] = []


class CredentialIn(BaseModel):
    provider_key: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    label: str = Field(min_length=1, max_length=80)
    secret: str = Field(min_length=8, max_length=512, repr=False)


class CredentialOut(BaseModel):
    id: UUID
    provider_key: str
    provider_name: str
    label: str
    secret_hint: str
    status: str
    last_verified_at: datetime | None
    last_error: str | None
    created_at: datetime


class RouteIn(BaseModel):
    model_id: UUID
    credential_id: UUID | None = None


class RoutesIn(BaseModel):
    routes: list[RouteIn] = Field(max_length=5)


class RouteOut(BaseModel):
    priority: int
    model_id: UUID
    model: str
    provider: str
    credential_id: UUID | None
    credential_label: str | None


class KindRoutesOut(BaseModel):
    kind: str
    source: Literal["organisation", "platform default", "none"]
    routes: list[RouteOut]


class CheckOut(BaseModel):
    usable: list[dict]
    skipped: list[dict]


class ChatTestIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    system: str | None = Field(default=None, max_length=2000)
    language: str | None = Field(default=None, max_length=20)


class SpeechTestIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    language: str | None = Field(default=None, max_length=20)
    voice: str | None = Field(default=None, max_length=80)


class TranscribeTestIn(BaseModel):
    audio_base64: str = Field(min_length=8, max_length=7_000_000)
    mime: Literal["audio/wav", "audio/x-wav", "audio/mpeg", "audio/webm", "audio/ogg"] = "audio/wav"
    language: str | None = Field(default=None, max_length=20)


class TestOut(BaseModel):
    provider: str
    model: str
    account: str
    attempts: list[dict]
    skipped: list[dict]
    units: dict[str, float]
    text: str | None = None
    audio_base64: str | None = None
    mime: str | None = None
