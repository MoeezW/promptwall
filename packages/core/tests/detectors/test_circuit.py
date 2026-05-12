import time

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from promptwall.detectors.circuit import BreakerState, CircuitBreaker


def _advance_time_to(monkeypatch: pytest.MonkeyPatch, target: float) -> None:
    """Pin the breaker module's view of monotonic time to a fixed value."""
    monkeypatch.setattr(
        "promptwall.detectors.circuit.time.monotonic",
        lambda: target,
    )


async def test_starts_closed_and_admits_calls():
    breaker = CircuitBreaker()
    assert breaker.state == BreakerState.CLOSED
    assert await breaker.acquire() is True


async def test_opens_after_threshold_failures():
    breaker = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        await breaker.acquire()
        await breaker.record_failure()
    assert breaker.state == BreakerState.OPEN
    assert await breaker.acquire() is False


async def test_success_resets_failure_counter():
    breaker = CircuitBreaker(failure_threshold=3)
    for _ in range(2):
        await breaker.acquire()
        await breaker.record_failure()
    await breaker.acquire()
    await breaker.record_success()
    for _ in range(2):
        await breaker.acquire()
        await breaker.record_failure()
    assert breaker.state == BreakerState.CLOSED


async def test_recovers_via_half_open(monkeypatch: pytest.MonkeyPatch):
    breaker = CircuitBreaker(failure_threshold=2, recovery_seconds=10.0)
    for _ in range(2):
        await breaker.acquire()
        await breaker.record_failure()
    assert breaker.state == BreakerState.OPEN

    _advance_time_to(monkeypatch, time.monotonic() + 20.0)
    admitted = await breaker.acquire()
    assert admitted is True
    assert breaker.state == BreakerState.HALF_OPEN
    await breaker.record_success()
    assert breaker.state == BreakerState.CLOSED


async def test_half_open_failure_reopens(monkeypatch: pytest.MonkeyPatch):
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=1.0)
    await breaker.acquire()
    await breaker.record_failure()
    _advance_time_to(monkeypatch, time.monotonic() + 100.0)
    await breaker.acquire()
    await breaker.record_failure()
    assert breaker.state == BreakerState.OPEN


async def test_half_open_caps_concurrent_probes(monkeypatch: pytest.MonkeyPatch):
    breaker = CircuitBreaker(
        failure_threshold=1,
        recovery_seconds=1.0,
        half_open_max_probes=1,
    )
    await breaker.acquire()
    await breaker.record_failure()
    _advance_time_to(monkeypatch, time.monotonic() + 100.0)
    first = await breaker.acquire()
    second = await breaker.acquire()
    assert first is True
    assert second is False


# --- property tests ---

_ACTION = st.sampled_from(["success", "failure", "acquire"])
_VALID_STATES = {BreakerState.CLOSED, BreakerState.OPEN, BreakerState.HALF_OPEN}


@given(actions=st.lists(_ACTION, min_size=0, max_size=50))
@hyp_settings(max_examples=50, deadline=None)
async def test_state_is_always_one_of_three(actions: list[str]):
    breaker = CircuitBreaker(failure_threshold=3, recovery_seconds=0.01)
    for action in actions:
        if action == "acquire":
            await breaker.acquire()
        elif action == "success":
            await breaker.record_success()
        else:
            await breaker.record_failure()
        assert breaker.state in _VALID_STATES


@given(
    threshold=st.integers(min_value=1, max_value=10),
    failures=st.integers(min_value=1, max_value=20),
)
@hyp_settings(max_examples=30, deadline=None)
async def test_consecutive_failures_eventually_open(threshold: int, failures: int):
    breaker = CircuitBreaker(failure_threshold=threshold, recovery_seconds=10_000)
    for _ in range(failures):
        await breaker.acquire()
        await breaker.record_failure()
    if failures >= threshold:
        assert breaker.state == BreakerState.OPEN
