"""Detector protocol and result DTOs.

Score semantics: ``0.0`` means certainly benign, ``1.0`` certainly
malicious. Detectors must not raise on malformed input — return a
``DetectorResult`` with ``score=0.0, matched=False`` and the error in
``metadata``. The runner's circuit breaker handles repeated failures.

Detectors are stateless after construction. Model weights load in
``__init__`` (or a FastAPI lifespan); no global mutable state.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class Span(BaseModel):
    """Character range that triggered a detection."""

    model_config = ConfigDict(frozen=True)

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    label: str | None = None


class DetectorResult(BaseModel):
    """Output of a single detector run."""

    model_config = ConfigDict(frozen=True)

    detector: str
    score: float = Field(ge=0.0, le=1.0)
    matched: bool
    spans: list[Span] = Field(default_factory=list)
    metadata: Mapping[str, object] = Field(default_factory=dict)
    latency_ms: float = Field(ge=0.0)
    degraded: bool = False


@dataclass(frozen=True)
class ScanContext:
    """Per-request context shared across detectors in one scan."""

    request_id: str
    direction: str  # "input" or "output"


@runtime_checkable
class Detector(Protocol):
    """The contract every detector implements.

    ``timeout_ms`` is per-call; the runner enforces it via
    ``asyncio.timeout``. ``scan`` must not raise on bad input.
    """

    name: str
    timeout_ms: int

    async def scan(self, text: str, ctx: ScanContext) -> DetectorResult:
        """Score ``text`` and return the result. Must not raise."""
        ...
