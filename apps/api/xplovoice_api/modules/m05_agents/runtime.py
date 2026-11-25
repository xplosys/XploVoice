# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Turns a stored agent version into what the voice engine runs: the composed system prompt, the business-hours
decision for this moment, and the flat settings the engine reads. Done on the server so a worker never decides
policy (guardrails, hours, escalation) itself."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .schemas import DAYS, AgentConfig, BusinessHours

TONES = {
    "friendly": "friendly and approachable",
    "professional": "professional and polished",
    "warm": "warm and caring",
    "calm": "calm and reassuring",
    "energetic": "upbeat and energetic",
    "concise": "brief and to the point",
}

# Always added for healthcare administrative agents, whatever the tenant writes (MP section 21: no clinical
# diagnosis, prescribing or clinical triage). Not a template field, so it cannot be edited away.
HEALTHCARE_GUARDRAIL = (
    "Safety rules you must always follow: you are an administrative assistant only. Do not give medical advice, "
    "do not diagnose, do not suggest or discuss medicines or doses, and do not assess how urgent a symptom is. "
    "If a caller describes symptoms or asks for medical advice, say that you can't help with medical questions "
    "and offer to pass a message to the clinic staff. If the caller says it is an emergency, tell them to hang "
    "up and call their local emergency number now. Ask only for the details needed to handle the request."
)

DAY_NAMES = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}


def is_open(hours: BusinessHours, at: datetime) -> bool:
    """True when business hours are off, or `at` (timezone-aware) falls in one of today's windows in the agent's
    time zone. Windows are half-open: 09:00-18:00 is open at 09:00 and closed at 18:00."""
    if not hours.enabled:
        return True
    local = at.astimezone(ZoneInfo(hours.timezone))
    hhmm = local.strftime("%H:%M")
    return any(w.start <= hhmm < w.end for w in hours.weekly.get(DAYS[local.weekday()], []))


def hours_summary(hours: BusinessHours) -> str:
    if not hours.enabled:
        return ""
    parts = []
    for d in DAYS:
        wins = hours.weekly.get(d, [])
        parts.append(f"{DAY_NAMES[d]}: " + (", ".join(f"{w.start}-{w.end}" for w in wins) if wins else "closed"))
    return f"Business hours ({hours.timezone}): " + "; ".join(parts) + "."


def system_prompt(cfg: AgentConfig, agent_name: str) -> str:
    lines = [cfg.system_prompt.strip()]
    if cfg.business_purpose.strip():
        lines.append(f"Your purpose: {cfg.business_purpose.strip()}")
    style = f"Speak in a {TONES[cfg.tone]} way."
    if cfg.personality.strip():
        style += f" Personality: {cfg.personality.strip()}"
    lines.append(style)
    lines.append(f"Your name is {agent_name}.")
    if summary := hours_summary(cfg.business_hours):
        lines.append(summary)
    if cfg.escalation.enabled:
        lines.append(
            "If the caller asks for a person, don't argue: say you'll arrange it. The system then hands the call over."
        )
    if cfg.agent_type == "healthcare_admin":
        lines.append(HEALTHCARE_GUARDRAIL)
    return "\n\n".join(x for x in lines if x)


def engine_config(cfg: AgentConfig, agent_name: str, *, open_now: bool, max_seconds_cap: int) -> dict[str, Any]:
    """The flat settings the engine reads. Keys are stable across agent schema changes."""
    esc = cfg.escalation
    escalation_message = cfg.transfer.announce if esc.action == "transfer" and cfg.transfer.enabled else esc.message
    return {
        "instructions": system_prompt(cfg, agent_name),
        "greeting": cfg.greeting,
        "language": cfg.language,
        "voice": cfg.ai.voice,
        "max_call_seconds": min(cfg.limits.max_call_seconds, max_seconds_cap),
        "silence_timeout_seconds": cfg.limits.silence_timeout_seconds,
        "endpoint_silence_ms": cfg.interruption.endpoint_silence_ms,
        "barge_in_min_ms": cfg.interruption.barge_in_min_ms,
        "interruptible": cfg.interruption.interruptible,
        "closed": None if open_now or cfg.business_hours.after_hours == "answer" else cfg.business_hours.closed_message,
        "escalation": {
            "enabled": esc.enabled,
            "phrases": esc.phrases,
            "max_unclear_turns": esc.max_unclear_turns,
            "action": esc.action if esc.action != "transfer" or cfg.transfer.enabled else "take_message",
            "message": escalation_message,
        },
        "messages": {
            "unavailable": cfg.fallback.provider_failure_message,
            "unclear": cfg.fallback.unclear_message,
        },
    }
