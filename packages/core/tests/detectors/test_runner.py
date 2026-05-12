import asyncio

from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from promptwall.detectors.base import DetectorResult, ScanContext
from promptwall.detectors.circuit import BreakerState, CircuitBreaker
from promptwall.detectors.runner import run_detectors

_CTX = ScanContext(request_id="test", direction="input")


class _FakeDetector:
    def __init__(
        self,
        name: str,
        score: float = 0.0,
        *,
        raises: bool = False,
        sleep: float = 0.0,
        timeout_ms: int = 100,
    ) -> None:
        self.name = name
        self.timeout_ms = timeout_ms
        self._score = score
        self._raises = raises
        self._sleep = sleep

    async def scan(self, _text: str, _ctx: ScanContext) -> DetectorResult:
        if self._sleep:
            await asyncio.sleep(self._sleep)
        if self._raises:
            msg = "simulated detector crash"
            raise RuntimeError(msg)
        return DetectorResult(
            detector=self.name,
            score=self._score,
            matched=self._score >= 0.5,
            latency_ms=1.0,
        )


class _SentinelDetector:
    """Records whether scan() was invoked — used to assert shedding."""

    name = "sentinel"
    timeout_ms = 100

    def __init__(self) -> None:
        self.called = False

    async def scan(self, _text: str, _ctx: ScanContext) -> DetectorResult:
        self.called = True
        return DetectorResult(
            detector=self.name,
            score=0.0,
            matched=False,
            latency_ms=0.0,
        )


async def test_runs_all_detectors_in_parallel():
    a = _FakeDetector("a", score=0.1)
    b = _FakeDetector("b", score=0.9)
    c = _FakeDetector("c", score=0.5)
    results = await run_detectors([a, b, c], "hi", _CTX)
    by_name = {r.detector: r for r in results}
    assert by_name["a"].score == 0.1
    assert by_name["b"].score == 0.9
    assert by_name["c"].score == 0.5


async def test_one_detector_raising_does_not_break_the_others():
    good = _FakeDetector("good", score=0.7)
    bad = _FakeDetector("bad", raises=True)
    results = await run_detectors([good, bad], "hi", _CTX)
    by_name = {r.detector: r for r in results}
    assert by_name["good"].matched is True
    assert by_name["bad"].degraded is True
    assert by_name["bad"].metadata["reason"] == "exception"


async def test_timeout_marks_detector_degraded():
    slow = _FakeDetector("slow", sleep=0.1, timeout_ms=10)
    results = await run_detectors([slow], "hi", _CTX)
    assert results[0].degraded is True
    assert results[0].metadata["reason"] == "timeout"


async def test_open_breaker_sheds_the_call_without_invoking_scan():
    sentinel = _SentinelDetector()
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=10_000)
    await breaker.acquire()
    await breaker.record_failure()
    assert breaker.state == BreakerState.OPEN

    results = await run_detectors(
        [sentinel],
        "hi",
        _CTX,
        {"sentinel": breaker},
    )
    assert sentinel.called is False
    assert results[0].degraded is True
    assert results[0].metadata["reason"] == "breaker_open"


async def test_breaker_records_success_on_normal_return():
    breaker = CircuitBreaker(failure_threshold=3)
    detector = _FakeDetector("ok", score=0.2)
    for _ in range(2):
        await breaker.acquire()
        await breaker.record_failure()
    await run_detectors([detector], "hi", _CTX, {"ok": breaker})
    assert breaker.state == BreakerState.CLOSED
    for _ in range(2):
        await breaker.acquire()
        await breaker.record_failure()
    assert breaker.state == BreakerState.CLOSED


_BEHAVIOR = st.sampled_from(["normal", "raises", "timeout"])


@given(behaviors=st.lists(_BEHAVIOR, min_size=1, max_size=8))
@hyp_settings(max_examples=25, deadline=None)
async def test_runner_returns_one_result_per_detector_regardless_of_behavior(
    behaviors: list[str],
):
    detectors = [
        _FakeDetector(
            name=f"d{i}",
            raises=(b == "raises"),
            sleep=(0.05 if b == "timeout" else 0.0),
            timeout_ms=(5 if b == "timeout" else 100),
        )
        for i, b in enumerate(behaviors)
    ]
    results = await run_detectors(detectors, "hi", _CTX)
    assert len(results) == len(detectors)
    assert {r.detector for r in results} == {d.name for d in detectors}
    for r in results:
        assert 0.0 <= r.score <= 1.0
        assert r.latency_ms >= 0.0
