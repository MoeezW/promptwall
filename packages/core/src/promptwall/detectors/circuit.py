"""Async-aware per-detector circuit breaker.

Standard three-state FSM: closed → open after N consecutive failures, open
→ half_open after a recovery window, half_open → closed on a successful
probe (or → open on a failed one). One instance per detector. Thread- and
coroutine-safe via a single ``asyncio.Lock``.
"""

import asyncio
import time
from enum import StrEnum

_DEFAULT_FAILURE_THRESHOLD = 5
_DEFAULT_RECOVERY_SECONDS = 30.0
_DEFAULT_HALF_OPEN_MAX_PROBES = 1


class BreakerState(StrEnum):
    """Circuit-breaker FSM states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """In-memory circuit breaker with closed | open | half_open states.

    Callers must:
        1. ``await acquire()`` — if ``False``, the call is shed.
        2. Run the protected work.
        3. ``await record_success()`` or ``await record_failure()``.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
        recovery_seconds: float = _DEFAULT_RECOVERY_SECONDS,
        half_open_max_probes: int = _DEFAULT_HALF_OPEN_MAX_PROBES,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._half_open_max_probes = half_open_max_probes
        self._state = BreakerState.CLOSED
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open_probes = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> BreakerState:
        """Current FSM state. Read without the lock — eventually consistent."""
        return self._state

    async def acquire(self) -> bool:
        """Try to admit a call.

        Returns ``False`` when the breaker is open and the call should be
        shed. On the transition open → half_open the first ``half_open_max_probes``
        callers are admitted as probes.
        """
        async with self._lock:
            if self._state == BreakerState.OPEN:
                elapsed = time.monotonic() - (self._opened_at or 0.0)
                if elapsed < self._recovery_seconds:
                    return False
                self._state = BreakerState.HALF_OPEN
                self._half_open_probes = 0

            if self._state == BreakerState.HALF_OPEN:
                if self._half_open_probes >= self._half_open_max_probes:
                    return False
                self._half_open_probes += 1
                return True

            return True

    async def record_success(self) -> None:
        """Report a successful call.

        Closes the breaker from half_open; resets the failure counter
        when closed; no-op when open (shouldn't happen if acquire() works).
        """
        async with self._lock:
            if self._state == BreakerState.HALF_OPEN:
                self._reset_locked()
            elif self._state == BreakerState.CLOSED:
                self._failures = 0

    async def record_failure(self) -> None:
        """Report a failed call.

        From half_open: immediately back to open. From closed: increment
        the failure counter and open when the threshold is reached.
        """
        async with self._lock:
            if self._state == BreakerState.HALF_OPEN:
                self._trip_locked()
            elif self._state == BreakerState.CLOSED:
                self._failures += 1
                if self._failures >= self._failure_threshold:
                    self._trip_locked()

    def _trip_locked(self) -> None:
        self._state = BreakerState.OPEN
        self._opened_at = time.monotonic()
        self._half_open_probes = 0

    def _reset_locked(self) -> None:
        self._state = BreakerState.CLOSED
        self._failures = 0
        self._opened_at = None
        self._half_open_probes = 0
