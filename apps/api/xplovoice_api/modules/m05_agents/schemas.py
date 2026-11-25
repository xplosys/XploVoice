# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 3 minimal agent configuration: what the voice engine needs to hold a conversation. The full agent
builder (MP section 9 fields, templates, publish and rollback) replaces this editing surface in Phase 4; the
engine reads the same pinned, immutable version either way."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Language = Literal["en-IN", "hi-IN", "hi-Latn-IN", "en-US"]


class AgentConfig(BaseModel):
    greeting: str = Field(default="Hello, thanks for calling. How can I help you today?", max_length=500)
    instructions: str = Field(
        default="You are a helpful, concise voice assistant. Keep replies to one or two short sentences.",
        max_length=8000,
    )
    language: Language = "en-IN"
    voice: str | None = Field(default=None, max_length=80)
    max_call_seconds: int = Field(default=300, ge=30, le=900)
    silence_timeout_seconds: int = Field(default=15, ge=5, le=60)
    endpoint_silence_ms: int = Field(default=600, ge=200, le=2000)
    barge_in_min_ms: int = Field(default=250, ge=100, le=1500)
    interruptible: bool = True


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    config: AgentConfig = AgentConfig()


class AgentOut(BaseModel):
    id: UUID
    name: str
    status: str
    version: int
    version_id: UUID
    config: AgentConfig
    updated_at: datetime


class VersionOut(BaseModel):
    id: UUID
    version: int
    created_at: datetime
