# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class VoiceSessionIn(BaseModel):
    agent_id: UUID
    version_id: UUID | None = None  # test a specific saved version; default: the latest
    simulate_after_hours: bool = False  # test the agent's after-hours behaviour at any time of day


class VoiceSessionOut(BaseModel):
    call_id: UUID
    room: str
    livekit_url: str
    token: str
    expires_in: int


class ChatStartIn(BaseModel):
    version_id: UUID | None = None


class ChatStartOut(BaseModel):
    call_id: UUID
    agent_name: str
    version: int
    greeting: str | None


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class ChatReplyOut(BaseModel):
    reply: str
    tools: list[dict[str, Any]]
    retrieval: list[dict[str, Any]]
    ended: bool
    end_reason: str | None


class CallOut(BaseModel):
    id: UUID
    agent_id: UUID
    agent_name: str
    agent_version: int
    channel: str
    direction: str
    status: str
    end_reason: str | None
    language: str | None
    created_at: datetime
    connected_at: datetime | None
    ended_at: datetime | None
    duration_seconds: Decimal | None
    recoveries: int
    agent_version_id: UUID
    providers_used: dict[str, Any] = {}


class SegmentOut(BaseModel):
    seq: int
    speaker: str
    text: str
    language: str | None
    start_ms: int | None
    end_ms: int | None
    interrupted: bool


class EventOut(BaseModel):
    type: str
    data: dict[str, Any]
    occurred_at: datetime


class CallDetailOut(CallOut):
    transcript: list[SegmentOut]
    events: list[EventOut]


# ------------------------------------------------------------------ worker (internal) API
class BootstrapIn(BaseModel):
    worker_id: str = Field(min_length=1, max_length=120)


class HistoryItem(BaseModel):
    speaker: str
    text: str


class BootstrapOut(BaseModel):
    call_id: UUID
    tenant_id: UUID
    correlation_id: str
    status: str
    agent_name: str
    agent_version: int
    config: dict[str, Any]
    room: str
    livekit_url: str
    livekit_token: str
    resumed: bool
    history: list[HistoryItem]
    next_seq: int
    elapsed_seconds: float


class StateIn(BaseModel):
    status: Literal["connecting", "active", "ending", "completed", "failed", "abandoned"]
    reason: str | None = Field(default=None, max_length=40)


class EventIn(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=60)
    data: dict[str, Any] = {}


class SegmentIn(BaseModel):
    seq: int = Field(ge=0)
    speaker: Literal["caller", "agent"]
    text: str = Field(max_length=8000)
    language: str | None = Field(default=None, max_length=20)
    start_ms: int | None = None
    end_ms: int | None = None
    interrupted: bool = False


class RecordIn(BaseModel):
    events: list[EventIn] = Field(default=[], max_length=100)
    segments: list[SegmentIn] = Field(default=[], max_length=50)


class WorkerSttIn(BaseModel):
    request_id: str = Field(min_length=8, max_length=80)
    audio_base64: str = Field(max_length=4_000_000)
    mime: str = "audio/wav"
    language: str | None = None


class WorkerMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=16000)


class WorkerLlmIn(BaseModel):
    request_id: str = Field(min_length=8, max_length=80)
    messages: list[WorkerMessage] = Field(min_length=1, max_length=200)
    language: str | None = None
    max_tokens: int = Field(default=300, ge=16, le=2000)


class WorkerTtsIn(BaseModel):
    request_id: str = Field(min_length=8, max_length=80)
    text: str = Field(min_length=1, max_length=1000)
    language: str | None = None
    voice: str | None = None


class WorkerAiOut(BaseModel):
    provider: str
    model: str
    account: str
    attempts: list[dict[str, Any]]
    text: str | None = None
    language: str | None = None
    audio_base64: str | None = None
    mime: str | None = None
