"""OpenAI-compatible safety-gateway proxy.

``POST /v1/chat/completions`` forwards to OpenAI, persists a row in the
``requests`` table, and emits an OpenTelemetry trace. Detectors are wired
in starting in Phase 2; streaming SSE pass-through is Phase 6.5.
"""

import hashlib
import json
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from promptwall import telemetry
from promptwall.db import close_engine, get_session
from promptwall.models import RequestRecord
from promptwall.providers.openai import OpenAIAdapter
from promptwall.settings import get_settings

log = structlog.get_logger()
tracer = trace.get_tracer("promptwall.proxy")

_SECONDS_TO_MS = 1000.0
_HASH_PREVIEW_CHARS = 16


class ChatMessage(BaseModel):
    """Minimal validation — full schema lives upstream at OpenAI."""

    model_config = ConfigDict(extra="allow")

    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """Permissive view of OpenAI's chat-completions request body.

    We validate the fields we touch (``model``, ``messages``, ``stream``)
    and accept everything else verbatim; the raw dict is what's forwarded.
    """

    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[ChatMessage]
    stream: bool = False


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    telemetry.configure(settings)
    app.state.openai = OpenAIAdapter(settings)
    log.info("proxy.startup", base_url=settings.openai_base_url)
    try:
        yield
    finally:
        adapter = getattr(app.state, "openai", None)
        if isinstance(adapter, OpenAIAdapter):
            await adapter.aclose()
        await close_engine()
        log.info("proxy.shutdown")


app = FastAPI(lifespan=_lifespan, title="promptwall", version="0.1.0")


def get_adapter(request: Request) -> OpenAIAdapter:
    """FastAPI dependency — pull the adapter off app.state with a type check.

    Tests override this via ``app.dependency_overrides[get_adapter]``.
    """
    adapter = getattr(request.app.state, "openai", None)
    if adapter is None:
        msg = "OpenAI adapter not initialized; lifespan did not run"
        raise RuntimeError(msg)
    if not isinstance(adapter, OpenAIAdapter):
        msg = f"app.state.openai is {type(adapter).__name__}, not OpenAIAdapter"
        raise TypeError(msg)
    return adapter


@app.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    adapter: Annotated[OpenAIAdapter, Depends(get_adapter)],
) -> JSONResponse:
    """Forward an OpenAI chat completion through the proxy."""
    payload = body.model_dump()
    request_hash = _hash_payload(payload)

    with tracer.start_as_current_span("proxy.chat.completions") as span:
        span.set_attribute("model", body.model)
        span.set_attribute("request.hash", request_hash)
        span.set_attribute("stream", body.stream)

        start = time.perf_counter()
        with tracer.start_as_current_span("provider.openai.forward"):
            response = await adapter.forward(payload)
        latency_ms = (time.perf_counter() - start) * _SECONDS_TO_MS

        span.set_attribute("http.status_code", response.status_code)
        span.set_attribute("latency_ms", latency_ms)

    await _persist_request(
        session,
        request_hash=request_hash,
        model=body.model,
        latency_ms=latency_ms,
        status=response.status_code,
    )
    log.info(
        "proxy.chat.completions.done",
        request_hash=request_hash[:_HASH_PREVIEW_CHARS],
        model=body.model,
        status=response.status_code,
        latency_ms=round(latency_ms, 2),
    )

    return JSONResponse(content=response.json(), status_code=response.status_code)


def _hash_payload(payload: Mapping[str, object]) -> str:
    """SHA-256 of the canonical JSON serialization."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


async def _persist_request(
    session: AsyncSession,
    *,
    request_hash: str,
    model: str,
    latency_ms: float,
    status: int,
) -> None:
    record = RequestRecord(
        request_hash=request_hash,
        model=model,
        latency_ms=latency_ms,
        status=status,
    )
    session.add(record)
    await session.commit()
