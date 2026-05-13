"""OpenAI-compatible safety-gateway proxy.

The Phase 4 flow per request:

1. Hash the canonical payload (SHA-256).
2. Extract the last ``user`` message content as scan text.
3. Run every enabled detector concurrently (TaskGroup + circuit breakers).
4. Evaluate the YAML policy against the detector results.
5. ``block`` → return 403 without forwarding.
   ``redact`` → replace PII spans with HMAC tokens, forward redacted payload.
   ``allow`` → forward as-is.
6. Hydrate the upstream response (substituting known tokens back to originals).
7. Persist the request envelope + the decision into Postgres.

Detectors, breakers, and the policy are wired via FastAPI dependencies so
tests can override them without touching the live providers.
"""

import hashlib
import json
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Annotated, Any

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from promptwall import telemetry
from promptwall.api import router as api_router
from promptwall.config import Action, DetectorConfig, Policy, load_policy
from promptwall.db import close_engine, get_session
from promptwall.detectors.base import Detector, DetectorResult, ScanContext
from promptwall.detectors.circuit import CircuitBreaker
from promptwall.detectors.injection_regex import InjectionRegexDetector
from promptwall.detectors.pii import PIIDetector
from promptwall.detectors.runner import run_detectors
from promptwall.detectors.secrets import SecretsDetector
from promptwall.models import RequestRecord
from promptwall.policy import Decision, evaluate
from promptwall.providers.openai import OpenAIAdapter
from promptwall.redaction import RedactionMap, hydrate, redact
from promptwall.settings import Settings, get_settings

log = structlog.get_logger()
tracer = trace.get_tracer("promptwall.proxy")

_SECONDS_TO_MS = 1000.0
_HASH_PREVIEW_CHARS = 16
_BLOCKED_STATUS = 403


class ChatMessage(BaseModel):
    """Minimal validation — full schema lives upstream at OpenAI."""

    model_config = ConfigDict(extra="allow")

    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """Permissive view of OpenAI's chat-completions request body."""

    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[ChatMessage]
    stream: bool = False


_ENABLED_DEFAULT = DetectorConfig(enabled=True)


def _build_detectors(policy: Policy) -> list[Detector]:
    """Instantiate enabled detectors. ML is opt-in (~50 s cold-start)."""
    detectors: list[Detector] = []
    if policy.detectors.get("injection_regex", _ENABLED_DEFAULT).enabled:
        detectors.append(InjectionRegexDetector())
    if policy.detectors.get("secrets", _ENABLED_DEFAULT).enabled:
        detectors.append(SecretsDetector())
    if policy.detectors.get("pii", _ENABLED_DEFAULT).enabled:
        detectors.append(PIIDetector())
    ml_cfg = policy.detectors.get("injection_ml")
    if ml_cfg is not None and ml_cfg.enabled:
        # Lazy import: avoid loading ONNX/Torch unless the operator opts in.
        from promptwall.detectors.injection_ml import InjectionMLDetector

        detectors.append(InjectionMLDetector())
    return detectors


def _load_policy_or_empty(settings: Settings) -> Policy:
    try:
        return load_policy(settings.policy_path)
    except FileNotFoundError:
        log.warning("policy.file.missing", path=str(settings.policy_path))
        return Policy()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    telemetry.configure(settings)
    policy = _load_policy_or_empty(settings)
    detectors = _build_detectors(policy)
    breakers = {d.name: CircuitBreaker() for d in detectors}

    app.state.policy = policy
    app.state.detectors = detectors
    app.state.breakers = breakers
    app.state.openai = OpenAIAdapter(settings)
    log.info(
        "proxy.startup",
        base_url=settings.openai_base_url,
        rules=len(policy.rules),
        detectors=[d.name for d in detectors],
    )
    try:
        yield
    finally:
        adapter = getattr(app.state, "openai", None)
        if isinstance(adapter, OpenAIAdapter):
            await adapter.aclose()
        await close_engine()
        log.info("proxy.shutdown")


app = FastAPI(lifespan=_lifespan, title="promptwall", version="0.1.0")
app.include_router(api_router)


def get_adapter(request: Request) -> OpenAIAdapter:
    """Pull the OpenAI adapter off app.state with a type check."""
    adapter = getattr(request.app.state, "openai", None)
    if adapter is None:
        msg = "OpenAI adapter not initialized; lifespan did not run"
        raise RuntimeError(msg)
    if not isinstance(adapter, OpenAIAdapter):
        msg = f"app.state.openai is {type(adapter).__name__}, not OpenAIAdapter"
        raise TypeError(msg)
    return adapter


def get_detectors(request: Request) -> Sequence[Detector]:
    """Pull the configured detector pipeline off app.state."""
    detectors = getattr(request.app.state, "detectors", None)
    if detectors is None:
        msg = "Detectors not initialized; lifespan did not run"
        raise RuntimeError(msg)
    if not isinstance(detectors, list):
        msg = f"app.state.detectors is {type(detectors).__name__}, not list"
        raise TypeError(msg)
    return detectors


def get_breakers(request: Request) -> Mapping[str, CircuitBreaker]:
    """Pull the per-detector circuit breakers off app.state."""
    breakers = getattr(request.app.state, "breakers", None)
    if breakers is None:
        msg = "Breakers not initialized; lifespan did not run"
        raise RuntimeError(msg)
    if not isinstance(breakers, dict):
        msg = f"app.state.breakers is {type(breakers).__name__}, not dict"
        raise TypeError(msg)
    return breakers


def get_policy(request: Request) -> Policy:
    """Pull the active policy off app.state."""
    policy = getattr(request.app.state, "policy", None)
    if policy is None:
        msg = "Policy not initialized; lifespan did not run"
        raise RuntimeError(msg)
    if not isinstance(policy, Policy):
        msg = f"app.state.policy is {type(policy).__name__}, not Policy"
        raise TypeError(msg)
    return policy


@app.post("/v1/chat/completions")
async def chat_completions(  # noqa: PLR0913 -- FastAPI deps live in the signature
    body: ChatCompletionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    adapter: Annotated[OpenAIAdapter, Depends(get_adapter)],
    detectors: Annotated[Sequence[Detector], Depends(get_detectors)],
    breakers: Annotated[Mapping[str, CircuitBreaker], Depends(get_breakers)],
    policy: Annotated[Policy, Depends(get_policy)],
) -> JSONResponse:
    """Run detectors → policy → maybe redact → forward → maybe hydrate → respond."""
    request_start = time.perf_counter()
    payload = body.model_dump()
    request_hash = _hash_payload(payload)

    with tracer.start_as_current_span("proxy.chat.completions") as span:
        span.set_attribute("model", body.model)
        span.set_attribute("request.hash", request_hash)

        scan_text = _last_user_content(body.messages)
        ctx = ScanContext(request_id=request_hash, direction="input")

        with tracer.start_as_current_span("detectors.scan"):
            detector_results = await run_detectors(detectors, scan_text, ctx, breakers)
        decision = evaluate(policy, list(detector_results))
        span.set_attribute("policy.action", decision.action.value)
        if decision.matched_rule_index is not None:
            span.set_attribute("policy.matched_rule", decision.matched_rule_index)

        if decision.action == Action.BLOCK:
            return await _handle_block(
                session=session,
                request_hash=request_hash,
                model=body.model,
                request_start=request_start,
                decision=decision,
                detector_results=detector_results,
            )

        redaction_map: RedactionMap | None = None
        if decision.action == Action.REDACT:
            pii_spans = _pii_spans(detector_results)
            if pii_spans:
                redacted_text, redaction_map = redact(scan_text, pii_spans)
                payload = _replace_last_user_content(payload, redacted_text)

        with tracer.start_as_current_span("provider.openai.forward"):
            response = await adapter.forward(payload)
        forward_latency_ms = (time.perf_counter() - request_start) * _SECONDS_TO_MS

        response_data = response.json()
        if redaction_map is not None and redaction_map.tokens:
            response_data = _hydrate_json(response_data, redaction_map.tokens)

        span.set_attribute("http.status_code", response.status_code)
        span.set_attribute("latency_ms", forward_latency_ms)

    await _persist_request(
        session,
        request_hash=request_hash,
        model=body.model,
        latency_ms=forward_latency_ms,
        status=response.status_code,
        detector_results=_serialize_detector_results(detector_results),
        policy_decision=_serialize_decision(decision),
    )
    log.info(
        "proxy.chat.completions.done",
        request_hash=request_hash[:_HASH_PREVIEW_CHARS],
        model=body.model,
        status=response.status_code,
        latency_ms=round(forward_latency_ms, 2),
        action=decision.action.value,
        rule_index=decision.matched_rule_index,
    )
    return JSONResponse(content=response_data, status_code=response.status_code)


async def _handle_block(  # noqa: PLR0913 -- internal helper, all kwargs
    *,
    session: AsyncSession,
    request_hash: str,
    model: str,
    request_start: float,
    decision: Decision,
    detector_results: Sequence[DetectorResult],
) -> JSONResponse:
    latency_ms = (time.perf_counter() - request_start) * _SECONDS_TO_MS
    await _persist_request(
        session,
        request_hash=request_hash,
        model=model,
        latency_ms=latency_ms,
        status=_BLOCKED_STATUS,
        detector_results=_serialize_detector_results(detector_results),
        policy_decision=_serialize_decision(decision),
    )
    log.info(
        "proxy.chat.completions.blocked",
        request_hash=request_hash[:_HASH_PREVIEW_CHARS],
        model=model,
        reason=decision.reason,
        rule_index=decision.matched_rule_index,
    )
    return JSONResponse(
        content={
            "error": {
                "message": decision.reason or "blocked by policy",
                "type": "promptwall_policy_block",
            },
        },
        status_code=_BLOCKED_STATUS,
    )


def _last_user_content(messages: list[ChatMessage]) -> str:
    for msg in reversed(messages):
        if msg.role == "user":
            return msg.content
    return ""


def _replace_last_user_content(payload: dict[str, Any], redacted: str) -> dict[str, Any]:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return payload
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, dict) and msg.get("role") == "user":
            new_msg = dict(msg)
            new_msg["content"] = redacted
            messages[i] = new_msg
            break
    return payload


def _pii_spans(results: Sequence[DetectorResult]) -> list[Any]:
    for r in results:
        if r.detector == "pii" and r.matched:
            return list(r.spans)
    return []


def _hydrate_json(value: object, tokens: Mapping[str, str]) -> object:
    if isinstance(value, str):
        return hydrate(value, tokens)
    if isinstance(value, dict):
        return {k: _hydrate_json(v, tokens) for k, v in value.items()}
    if isinstance(value, list):
        return [_hydrate_json(item, tokens) for item in value]
    return value


def _hash_payload(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


async def _persist_request(  # noqa: PLR0913 -- internal helper, all kwargs
    session: AsyncSession,
    *,
    request_hash: str,
    model: str,
    latency_ms: float,
    status: int,
    detector_results: list[dict[str, object]] | None = None,
    policy_decision: dict[str, object] | None = None,
) -> None:
    record = RequestRecord(
        request_hash=request_hash,
        model=model,
        latency_ms=latency_ms,
        status=status,
        detector_results=detector_results,
        policy_decision=policy_decision,
    )
    session.add(record)
    await session.commit()


def _serialize_detector_results(
    results: Sequence[DetectorResult],
) -> list[dict[str, object]]:
    return [r.model_dump(mode="json") for r in results]


def _serialize_decision(decision: Decision) -> dict[str, object]:
    return {
        "action": decision.action.value,
        "reason": decision.reason,
        "matched_rule_index": decision.matched_rule_index,
        "degraded_detectors": list(decision.degraded_detectors),
    }
