# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Agent builder configuration (MP section 9). One `AgentConfig` is one immutable agent version: everything a
call needs is in it, so a call that pins a version behaves the same however the agent is edited later.

The 25 MP section 9 fields map onto this model as follows (name and description live on the agent itself):
agent name, description -> Agent; business purpose, agent type, system prompt, personality, tone, greeting,
language -> top level; LLM provider + model, STT provider, TTS provider, voice provider + voice -> `ai`
(a provider is chosen by choosing one of its models; a voice belongs to the chosen TTS model, so the voice
provider is the TTS model's provider); knowledge base, tool permissions -> `knowledge_base_ids`, `tools`
(executed from Phase 5); business hours -> `business_hours`; silence timeout, maximum call duration ->
`limits`; interruption -> `interruption`; escalation rules -> `escalation`; call transfer -> `transfer`
(executed by telephony, Phase 6); recording policy -> `recording` (recordings arrive in Phase 6);
fallback behaviour -> `fallback`."""

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

Language = Literal["en-IN", "hi-IN", "hi-Latn-IN", "en-US"]
AgentType = Literal[
    "receptionist",
    "customer_support",
    "appointment_booking",
    "lead_qualification",
    "sales_assistant",
    "faq_assistant",
    "service_booking",
    "follow_up",
    "healthcare_admin",
    "custom",
]
Tone = Literal["friendly", "professional", "warm", "calm", "energetic", "concise"]
Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAYS: tuple[Day, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Business tools an agent may be granted. The tool gateway that executes them is built in Phase 5 (M09/M11-M14);
# until then a grant is stored with the version and has no effect on calls.
TOOL_KEYS = (
    "check_availability",
    "book_appointment",
    "reschedule_appointment",
    "cancel_appointment",
    "create_lead",
    "create_ticket",
    "lookup_order",
    "send_sms_confirmation",
)
ToolKey = Literal[
    "check_availability",
    "book_appointment",
    "reschedule_appointment",
    "cancel_appointment",
    "create_lead",
    "create_ticket",
    "lookup_order",
    "send_sms_confirmation",
]

E164 = re.compile(r"^\+[1-9]\d{6,14}$")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class AiSelection(BaseModel):
    """Preferred models. Each must be one of the tenant's routed models for that kind; the gateway tries the
    preferred one first and still fails over to the rest of the tenant's routes."""

    llm_model_id: UUID | None = None
    stt_model_id: UUID | None = None
    tts_model_id: UUID | None = None
    voice: str | None = Field(default=None, max_length=80)


class Window(BaseModel):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        if not HHMM.match(v):
            raise ValueError("Times must be HH:MM (24-hour)")
        return v

    @model_validator(mode="after")
    def _order(self) -> "Window":
        if self.end <= self.start:
            raise ValueError("A business-hours window must end after it starts")
        return self


def _default_week() -> dict[str, list[Window]]:
    weekday = [Window(start="09:00", end="18:00")]
    return {d: (list(weekday) if d not in ("sat", "sun") else []) for d in DAYS}


class BusinessHours(BaseModel):
    enabled: bool = False  # off: the agent answers at any time
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    weekly: dict[Day, list[Window]] = Field(default_factory=_default_week)
    after_hours: Literal["answer", "closed_message"] = "closed_message"
    closed_message: str = Field(
        default="Thanks for calling. We're closed right now. Please call back during our business hours.",
        max_length=500,
    )

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown time zone") from None
        return v

    @field_validator("weekly")
    @classmethod
    def _windows(cls, v: dict[str, list[Window]]) -> dict[str, list[Window]]:
        for day, wins in v.items():
            if len(wins) > 4:
                raise ValueError(f"At most 4 windows per day ({day})")
            ordered = sorted(wins, key=lambda w: w.start)
            for a, b in zip(ordered, ordered[1:], strict=False):
                if b.start < a.end:
                    raise ValueError(f"Business-hours windows overlap on {day}")
        return {d: v.get(d, []) for d in DAYS}


class Limits(BaseModel):
    max_call_seconds: int = Field(default=300, ge=30, le=900)
    silence_timeout_seconds: int = Field(default=15, ge=5, le=60)


class Interruption(BaseModel):
    interruptible: bool = True
    barge_in_min_ms: int = Field(default=250, ge=100, le=1500)
    endpoint_silence_ms: int = Field(default=600, ge=200, le=2000)


class Escalation(BaseModel):
    enabled: bool = True
    phrases: list[str] = Field(
        default_factory=lambda: ["speak to a human", "talk to a person", "real person", "human agent", "manager"],
        max_length=20,
    )
    max_unclear_turns: int = Field(default=3, ge=0, le=10)  # 0: never escalate on unclear turns
    action: Literal["transfer", "take_message", "end_call"] = "take_message"
    message: str = Field(
        default="I'll make sure a member of our team gets back to you. Thank you for your patience.",
        max_length=500,
    )

    @field_validator("phrases")
    @classmethod
    def _phrases(cls, v: list[str]) -> list[str]:
        out = []
        for p in v:
            p = " ".join(p.lower().split())
            if not 2 <= len(p) <= 60:
                raise ValueError("Escalation phrases must be 2 to 60 characters")
            if p not in out:
                out.append(p)
        return out


class TransferTarget(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    number: str

    @field_validator("number")
    @classmethod
    def _e164(cls, v: str) -> str:
        v = v.replace(" ", "").replace("-", "")
        if not E164.match(v):
            raise ValueError("Transfer numbers must be in international format, for example +919812345678")
        return v


class Transfer(BaseModel):
    enabled: bool = False
    targets: list[TransferTarget] = Field(default_factory=list, max_length=5)
    announce: str = Field(default="Please hold while I connect you.", max_length=300)
    mode: Literal["warm", "cold"] = "cold"


class Recording(BaseModel):
    policy: Literal["off", "record", "ask_consent"] = "off"
    consent_message: str = Field(
        default="This call may be recorded for quality and training. Say no if you'd prefer it isn't.",
        max_length=300,
    )


class Fallback(BaseModel):
    provider_failure_message: str = Field(
        default="Sorry, I'm having trouble right now and can't continue this call. Please try again later.",
        max_length=300,
    )
    unclear_message: str = Field(default="Sorry, I didn't catch that. Could you say it again?", max_length=300)
    on_failure: Literal["end_call", "transfer"] = "end_call"


class AgentConfig(BaseModel):
    business_purpose: str = Field(default="", max_length=1000)
    agent_type: AgentType = "custom"
    system_prompt: str = Field(
        default="You are a helpful, concise voice assistant. Keep replies to one or two short sentences.",
        max_length=8000,
    )
    personality: str = Field(default="", max_length=500)
    tone: Tone = "friendly"
    greeting: str = Field(default="Hello, thanks for calling. How can I help you today?", max_length=500)
    language: Language = "en-IN"
    ai: AiSelection = Field(default_factory=AiSelection)
    knowledge_base_ids: list[UUID] = Field(default_factory=list, max_length=20)
    tools: list[ToolKey] = Field(default_factory=list)
    business_hours: BusinessHours = Field(default_factory=BusinessHours)
    limits: Limits = Field(default_factory=Limits)
    interruption: Interruption = Field(default_factory=Interruption)
    escalation: Escalation = Field(default_factory=Escalation)
    transfer: Transfer = Field(default_factory=Transfer)
    recording: Recording = Field(default_factory=Recording)
    fallback: Fallback = Field(default_factory=Fallback)

    @model_validator(mode="before")
    @classmethod
    def _upgrade_phase3(cls, data: Any) -> Any:
        """Phase 3 versions were flat; they stay immutable in the database and are read through this upgrade."""
        if not isinstance(data, dict) or "instructions" not in data:
            return data
        d = dict(data)
        d.setdefault("system_prompt", d.pop("instructions"))
        d.pop("instructions", None)
        if "voice" in d:
            d.setdefault("ai", {})["voice"] = d.pop("voice")
        lim = {k: d.pop(k) for k in ("max_call_seconds", "silence_timeout_seconds") if k in d}
        if lim:
            d.setdefault("limits", lim)
        intr = {k: d.pop(k) for k in ("interruptible", "barge_in_min_ms", "endpoint_silence_ms") if k in d}
        if intr:
            d.setdefault("interruption", intr)
        return d

    @field_validator("tools")
    @classmethod
    def _unique_tools(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    template_key: str | None = Field(default=None, max_length=40)
    config: AgentConfig | None = None  # with a template: overrides the template's starting configuration


class AgentUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    config: AgentConfig
    note: str | None = Field(default=None, max_length=200)  # what changed, shown in version history


class AgentOut(BaseModel):
    id: UUID
    name: str
    description: str
    status: str
    template_key: str | None
    version: int  # latest saved version: what test calls use
    version_id: UUID
    config: AgentConfig
    published_version: int | None
    published_version_id: UUID | None
    published_at: datetime | None
    has_unpublished_changes: bool
    updated_at: datetime


class VersionOut(BaseModel):
    id: UUID
    version: int
    created_at: datetime
    created_by: str | None
    note: str | None
    content_hash: str
    is_published: bool
    was_published: bool
    test_calls: int  # completed test calls on exactly this version


class VersionDetail(VersionOut):
    config: AgentConfig


class Check(BaseModel):
    key: str
    level: Literal["ok", "warning", "error"]
    message: str


class Readiness(BaseModel):
    version: int
    ready: bool  # no errors
    tested: bool  # a completed test call exists on this version
    checks: list[Check]


class PublishIn(BaseModel):
    version_id: UUID | None = None  # default: the latest saved version
    skip_test_reason: str | None = Field(default=None, min_length=10, max_length=300)


class RollbackIn(BaseModel):
    version_id: UUID
    reason: str | None = Field(default=None, max_length=300)


class PublicationOut(BaseModel):
    action: str
    version: int | None
    reason: str | None
    actor: str | None
    created_at: datetime


class TemplateOut(BaseModel):
    key: str
    name: str
    description: str
    category: str
    config: AgentConfig
