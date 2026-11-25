# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Adapter contract tests (M03): each vendor adapter is exercised against recorded response shapes through an
httpx MockTransport. No network, no real keys. Verifies parsing, usage in provider units, auth headers and error
classification."""

import asyncio
import base64
import io
import json
import wave

import httpx
import pytest

from xplovoice_api.modules.m03_ai.adapters import base
from xplovoice_api.modules.m03_ai.adapters.anthropic import AnthropicChat
from xplovoice_api.modules.m03_ai.adapters.base import (
    ChatMessage,
    Endpoint,
    LLMRequest,
    LLMUsage,
    ProviderError,
    wav_seconds,
)
from xplovoice_api.modules.m03_ai.adapters.deepgram import DeepgramSTT
from xplovoice_api.modules.m03_ai.adapters.elevenlabs import ElevenLabsTTS
from xplovoice_api.modules.m03_ai.adapters.openai import OpenAIChat, OpenAITranscribe
from xplovoice_api.modules.m03_ai.adapters.sarvam import SarvamSTT, SarvamTTS

REQ = LLMRequest(model="m", messages=[ChatMessage("system", "Be brief."), ChatMessage("user", "Namaste")])


def wav(seconds: float = 1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


@pytest.fixture
def transport():
    seen: list[httpx.Request] = []
    handler: dict = {}

    def route(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler["fn"](request)

    base.set_transport(httpx.MockTransport(route))
    yield seen, handler
    base.set_transport(None)


def collect(agen):
    async def go():
        return [e async for e in agen]

    return asyncio.run(go())


def sse(events: list[str]) -> httpx.Response:
    return httpx.Response(
        200, content="".join(f"data: {e}\n\n" for e in events).encode(), headers={"content-type": "text/event-stream"}
    )


def test_openai_stream_parses_text_and_reported_usage(transport):
    seen, h = transport
    h["fn"] = lambda r: sse(
        [
            json.dumps({"choices": [{"delta": {"content": "Hello"}}]}),
            json.dumps({"choices": [{"delta": {"content": " there"}}]}),
            json.dumps({"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 2}}),
            "[DONE]",
        ]
    )
    events = collect(OpenAIChat().stream_chat(Endpoint("https://api.example/v1", "sk-test"), REQ))
    assert "".join(e.text for e in events if hasattr(e, "text")) == "Hello there"
    assert events[-1] == LLMUsage(12, 2)
    req = seen[0]
    assert req.url.path == "/v1/chat/completions" and req.headers["authorization"] == "Bearer sk-test"
    body = json.loads(req.content)
    assert body["stream"] is True and body["stream_options"] == {"include_usage": True}


def test_self_hosted_openai_compatible_sends_no_auth_header(transport):
    seen, h = transport
    h["fn"] = lambda r: sse([json.dumps({"choices": [{"delta": {"content": "ok"}}]}), "[DONE]"])
    collect(OpenAIChat().stream_chat(Endpoint("http://ollama:11434/v1", None), REQ))
    assert "authorization" not in seen[0].headers


def test_anthropic_stream_usage_split_across_events(transport):
    seen, h = transport
    h["fn"] = lambda r: sse(
        [
            json.dumps({"type": "message_start", "message": {"usage": {"input_tokens": 20}}}),
            json.dumps({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hi"}}),
            json.dumps({"type": "message_delta", "usage": {"output_tokens": 3}}),
            json.dumps({"type": "message_stop"}),
        ]
    )
    events = collect(AnthropicChat().stream_chat(Endpoint("https://api.anthropic.example", "ak"), REQ))
    assert events[0].text == "Hi" and events[-1] == LLMUsage(20, 3)
    body = json.loads(seen[0].content)
    assert body["system"] == "Be brief." and all(m["role"] != "system" for m in body["messages"])
    assert seen[0].headers["x-api-key"] == "ak" and "anthropic-version" in seen[0].headers


def test_openai_transcription_meters_reported_duration(transport):
    _, h = transport
    h["fn"] = lambda r: httpx.Response(200, json={"text": "namaste", "language": "hindi", "duration": 2.5})
    r = asyncio.run(
        OpenAITranscribe().transcribe(
            Endpoint("https://api.example/v1", "k"), model="w", audio=wav(), mime="audio/wav", language="hi-IN"
        )
    )
    assert r.text == "namaste" and r.audio_seconds == 2.5


def test_deepgram_parses_transcript_and_duration(transport):
    seen, h = transport
    h["fn"] = lambda r: httpx.Response(
        200,
        json={
            "metadata": {"duration": 1.75},
            "results": {"channels": [{"alternatives": [{"transcript": "hello world"}]}]},
        },
    )
    r = asyncio.run(
        DeepgramSTT().transcribe(
            Endpoint("https://dg.example", "dgk"), model="nova", audio=wav(), mime="audio/wav", language="en-US"
        )
    )
    assert (r.text, r.audio_seconds) == ("hello world", 1.75)
    assert seen[0].headers["authorization"] == "Token dgk" and seen[0].url.params["language"] == "en-US"


def test_elevenlabs_returns_wav_audio_and_characters(transport):
    seen, h = transport
    h["fn"] = lambda r: httpx.Response(200, content=b"\x00\x00" * 1600, headers={"content-type": "audio/pcm"})
    r = asyncio.run(
        ElevenLabsTTS().synthesize(
            Endpoint("https://el.example", "xik"), model="multi", text="Hello!", voice="v1", language="en-US"
        )
    )
    assert r.mime == "audio/wav" and wav_seconds(r.audio) == 0.1 and r.characters == 6
    assert seen[0].url.path == "/v1/text-to-speech/v1" and seen[0].headers["xi-api-key"] == "xik"
    assert seen[0].url.params["output_format"] == "pcm_16000"


def test_sarvam_tts_decodes_base64_and_stt_meters_wav_length(transport):
    _, h = transport
    h["fn"] = lambda r: httpx.Response(200, json={"audios": [base64.b64encode(b"RIFFdata").decode()]})
    t = asyncio.run(
        SarvamTTS().synthesize(
            Endpoint("https://sv.example", "s"), model="bulbul", text="नमस्ते", voice=None, language="hi-IN"
        )
    )
    assert t.audio == b"RIFFdata" and t.characters == len("नमस्ते")
    h["fn"] = lambda r: httpx.Response(200, json={"transcript": "नमस्ते", "language_code": "hi-IN"})
    s = asyncio.run(
        SarvamSTT().transcribe(
            Endpoint("https://sv.example", "s"), model="saarika", audio=wav(3.0), mime="audio/wav", language="hi-IN"
        )
    )
    assert s.text == "नमस्ते" and abs(s.audio_seconds - 3.0) < 0.01


@pytest.mark.parametrize(
    ("code", "availability", "retryable"),
    [(401, False, False), (429, False, True), (503, True, True), (400, False, False)],
)
def test_error_classification_never_includes_response_body(transport, code, availability, retryable):
    _, h = transport
    h["fn"] = lambda r: httpx.Response(code, json={"error": "secret user prompt echoed here"})
    with pytest.raises(ProviderError) as e:
        collect(OpenAIChat().stream_chat(Endpoint("https://api.example/v1", "k"), REQ))
    assert (e.value.availability, e.value.retryable) == (availability, retryable)
    assert "secret user prompt" not in str(e.value)


def test_connection_failure_is_an_availability_error(transport):
    _, h = transport

    def boom(r):
        raise httpx.ConnectError("refused")

    h["fn"] = boom
    with pytest.raises(ProviderError) as e:
        asyncio.run(
            DeepgramSTT().transcribe(
                Endpoint("https://dg.example", "k"), model="nova", audio=wav(), mime="audio/wav", language=None
            )
        )
    assert e.value.availability is True
