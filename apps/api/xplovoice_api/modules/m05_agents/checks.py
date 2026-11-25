# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Readiness checks for an agent version. Errors block publishing; warnings explain what a setting will and won't
do today. Provider checks use the same routing the gateway uses, so "ready" means a call could actually be
served now."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..m03_ai.models import Model, PlatformRoute, TenantRoute
from ..m03_ai.routing import candidates
from .schemas import AgentConfig, Check

KIND_NAMES = {"llm": "language model", "stt": "speech-to-text", "tts": "text-to-speech"}


def _routed(session: Session, kind: str) -> list[UUID]:
    rows = session.scalars(
        select(TenantRoute.model_id).where(TenantRoute.kind == kind, TenantRoute.enabled.is_(True))
    ).all()
    if rows:
        return list(rows)
    return list(
        session.scalars(
            select(PlatformRoute.model_id).where(PlatformRoute.kind == kind, PlatformRoute.enabled.is_(True))
        )
    )


def _provider_checks(session: Session, cfg: AgentConfig) -> list[Check]:
    out: list[Check] = []
    prefs = {"llm": cfg.ai.llm_model_id, "stt": cfg.ai.stt_model_id, "tts": cfg.ai.tts_model_id}
    for kind, name in KIND_NAMES.items():
        usable, skipped = candidates(session, kind=kind, language=cfg.language, need_streaming=kind == "llm")
        pref = prefs[kind]
        if not usable:
            why = f" ({skipped[0].provider} {skipped[0].model}: {skipped[0].reason})" if skipped else ""
            out.append(
                Check(
                    key=f"provider.{kind}",
                    level="error",
                    message=f"No {name} provider can serve {cfg.language} calls right now{why}. "
                    "Set one up under AI providers.",
                )
            )
            continue
        if pref is None:
            first = usable[0]
            out.append(
                Check(
                    key=f"provider.{kind}",
                    level="ok",
                    message=f"{name.capitalize()}: your default route "
                    f"({first.provider.name} {first.model.display_name}).",
                )
            )
            continue
        model = session.get(Model, pref)
        label = model.display_name if model else "the chosen model"
        if pref not in _routed(session, kind) or model is None or model.kind != kind:
            out.append(
                Check(
                    key=f"provider.{kind}",
                    level="error",
                    message=f"The chosen {name} model ({label}) is not one of your AI routes. "
                    "Pick another model or add it to your routes.",
                )
            )
        elif usable[0].model.id != pref:
            reason = next((s.reason for s in skipped if s.model == model.display_name), "unavailable")
            out.append(
                Check(
                    key=f"provider.{kind}",
                    level="warning",
                    message=f"The chosen {name} model ({label}) can't be used now ({reason}). Calls will use "
                    f"{usable[0].provider.name} {usable[0].model.display_name} instead.",
                )
            )
        else:
            out.append(Check(key=f"provider.{kind}", level="ok", message=f"{name.capitalize()}: {label}."))
    if cfg.ai.voice and cfg.ai.tts_model_id:
        model = session.get(Model, cfg.ai.tts_model_id)
        ids = {v.get("id") for v in (model.voices if model else [])}
        if ids and cfg.ai.voice not in ids:
            out.append(
                Check(key="voice", level="error", message="The chosen voice isn't offered by the chosen TTS model.")
            )
    return out


def readiness(session: Session, cfg: AgentConfig) -> list[Check]:
    """Must run inside the tenant's RLS context."""
    out: list[Check] = []
    if not cfg.system_prompt.strip():
        out.append(Check(key="system_prompt", level="error", message="Write a system prompt for the agent."))
    if not cfg.greeting.strip():
        out.append(
            Check(key="greeting", level="warning", message="No greeting: callers hear nothing until they speak first.")
        )
    out += _provider_checks(session, cfg)

    t, esc, fb = cfg.transfer, cfg.escalation, cfg.fallback
    if t.enabled and not t.targets:
        out.append(
            Check(key="transfer", level="error", message="Call transfer is on but has no numbers to transfer to.")
        )
    if esc.enabled and esc.action == "transfer" and not t.enabled:
        out.append(
            Check(key="escalation", level="error", message="Escalation is set to transfer, but call transfer is off.")
        )
    if fb.on_failure == "transfer" and not t.enabled:
        out.append(
            Check(key="fallback", level="error", message="The fallback is set to transfer, but call transfer is off.")
        )
    if t.enabled:
        out.append(
            Check(
                key="transfer.runtime",
                level="warning",
                message="Transfers to a phone number are carried out by telephony (Phase 6). On a browser test call "
                "the agent says the hand-over message and ends the call.",
            )
        )
    if cfg.knowledge_base_ids:
        out.append(
            Check(
                key="knowledge_base",
                level="warning",
                message="Knowledge bases are connected in Phase 5. Until then the agent does not search them.",
            )
        )
    if cfg.tools:
        out.append(
            Check(
                key="tools",
                level="warning",
                message="Tool permissions are saved, but business tools run from Phase 5. Until then the agent "
                "can't book, look up or create anything.",
            )
        )
    if cfg.recording.policy != "off":
        out.append(
            Check(
                key="recording",
                level="warning",
                message="Call recording arrives with telephony and consent management (Phase 6). Calls are not "
                "recorded yet.",
            )
        )
    bh = cfg.business_hours
    if bh.enabled and not any(bh.weekly.get(d) for d in bh.weekly):
        out.append(
            Check(key="business_hours", level="warning", message="Business hours are on but every day is closed.")
        )
    if cfg.agent_type == "healthcare_admin":
        out.append(
            Check(
                key="healthcare",
                level="ok",
                message="Administrative-only safety rules are always added: no diagnosis, prescribing or triage. "
                "Use synthetic data only; health information must not be sent to providers without an approved BAA.",
            )
        )
    return out
