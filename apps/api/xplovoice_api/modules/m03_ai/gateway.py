# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""AI gateway (M03): runs a request against the routed candidates in order, with per-call timeouts, bounded
retries with exponential backoff and jitter, provider rate limits, circuit breakers and failover (addendum L).
Successful calls are metered in provider units (M15). Prompts, audio and replies are never logged or audited.

Database work happens in a thread (the request session is synchronous); provider I/O is async."""

import asyncio
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import redis
from prometheus_client import Counter, Histogram
from starlette.concurrency import run_in_threadpool

from ...core.config import get_settings
from ...core.ratelimit import client
from ..m15_usage import metering
from . import breaker
from .adapters import adapter_for
from .adapters.base import LLMRequest, LLMUsage, ProviderError, STTResult, TextDelta, TTSResult
from .routing import Candidate, Skipped, candidates

ATTEMPTS = Counter("xv_ai_attempts_total", "AI provider attempts", ["kind", "provider", "outcome"])
LATENCY = Histogram("xv_ai_latency_seconds", "AI provider latency (first byte for streams)", ["kind", "provider"])
MAX_TRIES_PER_CANDIDATE = 2


@dataclass
class Attempt:
    provider: str
    model: str
    outcome: str  # success | error | rate_limited | breaker_open
    error: str | None = None
    latency_ms: int | None = None


@dataclass
class Outcome:
    provider: str
    model: str
    account: str
    attempts: list[Attempt] = field(default_factory=list)
    skipped: list[Skipped] = field(default_factory=list)
    units: dict[str, float] = field(default_factory=dict)


class NoProviderAvailableError(Exception):
    def __init__(self, kind: str, attempts: list[Attempt], skipped: list[Skipped]) -> None:
        super().__init__(f"No {kind} provider could serve this request")
        self.kind = kind
        self.attempts = attempts
        self.skipped = skipped


@dataclass
class Meter:
    """What the gateway needs to meter a successful call. tenant_id comes from the verified session."""

    session: Any
    tenant_id: UUID
    idempotency_key: str
    source_type: str
    source_id: str | None = None
    correlation_id: str | None = None


def _provider_rate_ok(c: Candidate) -> bool:
    rpm = c.provider.rate_limit_rpm
    if not rpm:
        return True
    key = f"rl:prov:{c.provider.key}:{c.account}:{c.credential_id or 'managed'}:{int(time.time() // 60)}"
    try:
        n = client().incr(key)
        client().expire(key, 65)
    except redis.RedisError:
        return True
    return n <= rpm


def _backoff(n: int) -> float:
    return min(2.0, 0.2 * (2**n)) + random.uniform(0, 0.1)  # noqa: S311 - jitter, not security


async def _meter(m: Meter, c: Candidate, kind: str, units: dict[str, float], *, estimated: bool = False) -> None:
    def write() -> None:
        metering.record(
            m.session,
            tenant_id=m.tenant_id,
            idempotency_key=m.idempotency_key,
            kind=kind,
            provider_id=c.provider.id,
            model_id=c.model.id,
            account=c.account,
            credential_id=c.credential_id,
            units=units,
            source_type=m.source_type,
            source_id=m.source_id,
            correlation_id=m.correlation_id,
            estimated=estimated,
        )

    await run_in_threadpool(write)


def estimate_tokens(chars: int) -> int:
    """Rough token count (about four characters per token) used only when a provider never reported usage."""
    return max(1, -(-chars // 4))


async def _route(m: Meter, kind: str, **filters: Any) -> tuple[list[Candidate], list[Skipped]]:
    return await run_in_threadpool(lambda: candidates(m.session, kind=kind, **filters))


async def run[T](
    m: Meter,
    kind: str,
    call: Callable[[Any, Candidate], Awaitable[T]],
    units_of: Callable[[T], dict[str, float]],
    **filters: Any,
) -> tuple[T, Outcome]:
    """Non-streaming call (STT, TTS) with failover."""
    cands, skipped = await _route(m, kind, **filters)
    attempts: list[Attempt] = []
    timeout = get_settings().ai_request_timeout_seconds
    for c in cands:
        adapter = adapter_for(c.provider.adapter, kind)
        for n in range(MAX_TRIES_PER_CANDIDATE):
            if not breaker.allow(c.provider.key):
                attempts.append(Attempt(c.provider.name, c.model.display_name, "breaker_open"))
                break
            if not _provider_rate_ok(c):
                attempts.append(Attempt(c.provider.name, c.model.display_name, "rate_limited"))
                ATTEMPTS.labels(kind, c.provider.key, "rate_limited").inc()
                break
            start = time.perf_counter()
            try:
                result = await asyncio.wait_for(call(adapter, c), timeout)
            except (ProviderError, TimeoutError) as e:
                err = e if isinstance(e, ProviderError) else ProviderError(f"{c.provider.key}: timed out")
                ms = int((time.perf_counter() - start) * 1000)
                attempts.append(Attempt(c.provider.name, c.model.display_name, "error", str(err), ms))
                ATTEMPTS.labels(kind, c.provider.key, "error").inc()
                if err.availability:
                    breaker.failure(c.provider.key)
                if err.retryable and err.availability and n + 1 < MAX_TRIES_PER_CANDIDATE:
                    await asyncio.sleep(_backoff(n))
                    continue
                break
            ms = int((time.perf_counter() - start) * 1000)
            LATENCY.labels(kind, c.provider.key).observe(ms / 1000)
            ATTEMPTS.labels(kind, c.provider.key, "success").inc()
            breaker.success(c.provider.key)
            attempts.append(Attempt(c.provider.name, c.model.display_name, "success", latency_ms=ms))
            units = units_of(result)
            await _meter(m, c, kind, units)
            return result, Outcome(c.provider.name, c.model.display_name, c.account, attempts, skipped, units)
    raise NoProviderAvailableError(kind, attempts, skipped)


async def transcribe(
    m: Meter, *, audio: bytes, mime: str, language: str | None, phi: bool = False
) -> tuple[STTResult, Outcome]:
    return await run(
        m,
        "stt",
        lambda a, c: a.transcribe(c.endpoint, model=c.model.model_key, audio=audio, mime=mime, language=language),
        lambda r: {"audio_second": round(r.audio_seconds, 3)},
        language=language,
        phi=phi,
    )


async def synthesize(
    m: Meter, *, text: str, language: str | None, voice: str | None = None, phi: bool = False
) -> tuple[TTSResult, Outcome]:
    return await run(
        m,
        "tts",
        lambda a, c: a.synthesize(c.endpoint, model=c.model.model_key, text=text, voice=voice, language=language),
        lambda r: {"character": r.characters},
        language=language,
        phi=phi,
    )


async def chat_stream(
    m: Meter,
    req: LLMRequest,
    *,
    language: str | None,
    need_tools: bool = False,
    phi: bool = False,
    outcome: Outcome | None = None,
) -> AsyncIterator[str]:
    """Streams text with failover allowed only until the first token: after that, switching provider would
    repeat or contradict what the caller has already heard. Usage is metered when the provider reports it."""
    cands, skipped = await _route(m, "llm", language=language, need_streaming=True, need_tools=need_tools, phi=phi)
    attempts: list[Attempt] = []
    timeout = get_settings().ai_request_timeout_seconds
    for c in cands:
        adapter = adapter_for(c.provider.adapter, "llm")
        model_req = LLMRequest(
            model=c.model.model_key, messages=req.messages, max_tokens=req.max_tokens, temperature=req.temperature
        )
        for n in range(MAX_TRIES_PER_CANDIDATE):
            if not breaker.allow(c.provider.key):
                attempts.append(Attempt(c.provider.name, c.model.display_name, "breaker_open"))
                break
            if not _provider_rate_ok(c):
                attempts.append(Attempt(c.provider.name, c.model.display_name, "rate_limited"))
                break
            start = time.perf_counter()
            stream = adapter.stream_chat(c.endpoint, model_req)
            started = False
            usage: LLMUsage | None = None
            out_chars = 0
            try:
                async with asyncio.timeout(timeout):
                    async for ev in stream:
                        if isinstance(ev, TextDelta):
                            if not started:
                                started = True
                                LATENCY.labels("llm", c.provider.key).observe(time.perf_counter() - start)
                            out_chars += len(ev.text)
                            yield ev.text
                        elif isinstance(ev, LLMUsage):
                            usage = ev
            except (GeneratorExit, asyncio.CancelledError):
                # The consumer stopped early (barge-in, hang-up). Close the provider stream, then meter what was
                # consumed: the provider's figure when it sent one, otherwise a flagged estimate.
                await stream.aclose()  # type: ignore[attr-defined]
                if started:
                    if usage:
                        units = {"input_token": usage.input_tokens, "output_token": usage.output_tokens}
                        await _meter(m, c, "llm", units)
                    else:
                        in_chars = sum(len(msg.content) for msg in req.messages)
                        units = {"input_token": estimate_tokens(in_chars), "output_token": estimate_tokens(out_chars)}
                        await _meter(m, c, "llm", units, estimated=True)
                    breaker.success(c.provider.key)
                    if outcome is not None:
                        outcome.provider, outcome.model, outcome.account = (
                            c.provider.name,
                            c.model.display_name,
                            c.account,
                        )
                        outcome.attempts, outcome.skipped, outcome.units = attempts, skipped, units
                raise
            except (ProviderError, TimeoutError) as e:
                err = e if isinstance(e, ProviderError) else ProviderError(f"{c.provider.key}: timed out")
                ms = int((time.perf_counter() - start) * 1000)
                attempts.append(Attempt(c.provider.name, c.model.display_name, "error", str(err), ms))
                ATTEMPTS.labels("llm", c.provider.key, "error").inc()
                if err.availability:
                    breaker.failure(c.provider.key)
                if started:
                    if usage:
                        await _meter(
                            m, c, "llm", {"input_token": usage.input_tokens, "output_token": usage.output_tokens}
                        )
                    raise
                if err.retryable and err.availability and n + 1 < MAX_TRIES_PER_CANDIDATE:
                    await asyncio.sleep(_backoff(n))
                    continue
                break
            ms = int((time.perf_counter() - start) * 1000)
            ATTEMPTS.labels("llm", c.provider.key, "success").inc()
            breaker.success(c.provider.key)
            attempts.append(Attempt(c.provider.name, c.model.display_name, "success", latency_ms=ms))
            units = {"input_token": usage.input_tokens, "output_token": usage.output_tokens} if usage else {}
            if units:
                await _meter(m, c, "llm", units)
            if outcome is not None:
                outcome.provider, outcome.model, outcome.account = c.provider.name, c.model.display_name, c.account
                outcome.attempts, outcome.skipped, outcome.units = attempts, skipped, units
            return
    raise NoProviderAvailableError("llm", attempts, skipped)
