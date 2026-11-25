# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Adapter registry: (adapter name, kind) -> implementation."""

from .anthropic import AnthropicChat
from .base import LLMAdapter, STTAdapter, TTSAdapter
from .deepgram import DeepgramSTT
from .elevenlabs import ElevenLabsTTS
from .mock import MockChat, MockSTT, MockTTS
from .openai import OpenAIChat, OpenAISpeech, OpenAITranscribe
from .piper import PiperTTS
from .sarvam import SarvamSTT, SarvamTTS

REGISTRY: dict[tuple[str, str], LLMAdapter | STTAdapter | TTSAdapter] = {
    ("openai", "llm"): OpenAIChat(),
    ("openai", "stt"): OpenAITranscribe(),
    ("openai", "tts"): OpenAISpeech(),
    ("anthropic", "llm"): AnthropicChat(),
    ("deepgram", "stt"): DeepgramSTT(),
    ("elevenlabs", "tts"): ElevenLabsTTS(),
    ("sarvam", "stt"): SarvamSTT(),
    ("sarvam", "tts"): SarvamTTS(),
    ("piper", "tts"): PiperTTS(),
    ("mock", "llm"): MockChat(),
    ("mock", "stt"): MockSTT(),
    ("mock", "tts"): MockTTS(),
}


def adapter_for(adapter: str, kind: str):  # type: ignore[no-untyped-def]
    return REGISTRY.get((adapter, kind))
