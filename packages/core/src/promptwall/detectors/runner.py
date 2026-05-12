"""Parallel detector execution via ``asyncio.TaskGroup``.

This is the structural concurrency that distinguishes promptwall from a
sequential firewall. Every detector runs in parallel with its own
per-detector timeout, behind a circuit breaker that sheds it when it
misbehaves. The runner itself never raises — a misbehaving detector
produces a degraded ``DetectorResult``, not an exception.

Why TaskGroup and not ``asyncio.gather``: TaskGroup gives us structured
concurrency. If we somehow let an exception escape ``_run_one``, it
cancels siblings and surfaces in an ``ExceptionGroup`` rather than
silently abandoning tasks the way ``gather(return_exceptions=False)``
would.
"""

import asyncio
import time
from collections.abc import Mapping, Sequence

import structlog

from promptwall.detectors.base import Detector, DetectorResult, ScanContext
from promptwall.detectors.circuit import CircuitBreaker

log = structlog.get_logger()

_MS_PER_SECOND = 1000.0


async def run_detectors(
    detectors: Sequence[Detector],
    text: str,
    ctx: ScanContext,
    breakers: Mapping[str, CircuitBreaker] | None = None,
) -> list[DetectorResult]:
    """Run every detector concurrently. One result per detector, always."""
    breakers = breakers or {}
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(_run_one(d, text, ctx, breakers.get(d.name))) for d in detectors]
    return [task.result() for task in tasks]


async def _run_one(
    detector: Detector,
    text: str,
    ctx: ScanContext,
    breaker: CircuitBreaker | None,
) -> DetectorResult:
    if breaker is not None and not await breaker.acquire():
        return _degraded(detector.name, reason="breaker_open")

    start = time.perf_counter()
    try:
        async with asyncio.timeout(detector.timeout_ms / _MS_PER_SECOND):
            result = await detector.scan(text, ctx)
    except TimeoutError:
        if breaker is not None:
            await breaker.record_failure()
        return _degraded(
            detector.name,
            reason="timeout",
            latency_ms=_elapsed_ms(start),
        )
    except Exception as exc:
        # Detectors are contracted not to raise (see detectors/base.py); a
        # raised exception is a detector bug. The runner catches it here so
        # one buggy detector can't bring down the whole request path. The
        # circuit breaker absorbs repeated bugs by shedding the detector.
        log.exception(
            "detector.crash",
            detector=detector.name,
            request_id=ctx.request_id,
            error_type=type(exc).__name__,
        )
        if breaker is not None:
            await breaker.record_failure()
        return _degraded(
            detector.name,
            reason="exception",
            latency_ms=_elapsed_ms(start),
        )

    if breaker is not None:
        await breaker.record_success()
    return result


def _degraded(name: str, *, reason: str, latency_ms: float = 0.0) -> DetectorResult:
    return DetectorResult(
        detector=name,
        score=0.0,
        matched=False,
        latency_ms=latency_ms,
        degraded=True,
        metadata={"reason": reason},
    )


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * _MS_PER_SECOND
