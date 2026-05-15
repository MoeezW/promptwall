# ADR 0003 — Structured concurrency with per-detector circuit breakers

**Status:** Accepted
**Date:** 2026-04-25

## Context

A safety gateway runs N detectors per request. The naïve implementation runs them sequentially under one global timeout — fast detectors get budget stolen by slow ones, and a hung detector poisons every request that follows. Most portfolio firewalls and several commercial ones do exactly this.

Concurrency alone isn't enough. `asyncio.gather` runs tasks concurrently but on the first exception it cancels the rest *and* leaks the cancellation as an unhandled error if you forget the `return_exceptions=True` dance. Worse, a detector that's slow but eventually returns is not the same failure mode as one that's broken — and they need different responses.

The behaviors we need:

1. Run all enabled detectors in parallel.
2. Bound each detector's wall-clock latency individually.
3. When a detector repeatedly times out or errors, *shed* it from subsequent requests so it stops polluting tail latency.
4. Let the policy engine know which detectors were degraded so it can fall through to a configured `degraded_action` instead of pretending the missing signal was benign.

## Decision

Three concrete moving parts:

**`asyncio.TaskGroup`** (Python 3.11+) runs the detectors. TaskGroup gives us structured concurrency: a child failure cancels siblings cleanly, and the parent's `async with` exit synchronizes everything. We never call `asyncio.gather` for detector orchestration.

**Per-detector timeout** wraps each `Detector.scan(...)` call in `asyncio.timeout(detector.timeout_ms / 1000)`. A timeout returns a `DetectorResult` with `score=0.0`, `matched=False`, `metadata={"error": "timeout"}` and trips the circuit breaker — it does not propagate as an exception.

**Per-detector circuit breaker** is a three-state FSM (`closed | open | half_open`) per detector name. Defaults: 5 consecutive failures opens the breaker; after 30 seconds one probe is admitted (`half_open`); a success closes it. While open, the runner skips the detector entirely and returns a synthetic "degraded" result. State transitions are covered by a hypothesis property test in `tests/property/test_circuit.py`.

The pieces compose: TaskGroup runs the live detectors, each is wrapped in a timeout, failures and timeouts feed the breaker, and the breaker's state determines whether the detector even gets invoked next time.

## Consequences

**Good:**

- Total per-request latency is bounded by `max(detector_timeouts)`, not the sum. With the four current detectors, that's the ML detector at 50 ms — see `benchmarks/results.md` for measured p99.
- A model load that gets stuck doesn't take the request path down with it; the breaker opens and the policy engine sees `injection_ml: degraded`.
- The contract between the runner and a detector is a Protocol with one method (`scan`), which makes adding detectors mechanical and reviewing them quick.

**Tradeoffs:**

- The breaker's state lives in-process. A multi-instance deployment has per-instance breakers, which is fine for the failure mode it targets (a broken detector hangs *this* process) but doesn't aggregate across pods. Per-pod breakers are correct here; we'd need a shared store only if a detector's failure was specific to upstream state, which it isn't.
- The "degraded → block" default is conservative. An operator running with high-traffic ML detectors that occasionally time out will see a small `block` blip until they tune timeouts. The `degraded_action: block` setting is documented in `policies/default.yaml`.

## Rejected alternatives

- **`asyncio.gather` with `return_exceptions=True`.** Works, but the partial-failure semantics are ambient (every caller has to remember to check), and cancellation on the happy path is implicit. TaskGroup makes both explicit.
- **Sequential detectors with one global timeout.** Easier to implement. Hides the latency cost of the slow detector and makes per-detector budgeting impossible. This is the configuration the operational-maturity differentiator is *against*.
- **External circuit breaker (resilience4j-style library).** Pulls in a heavy dep for a 60-line FSM. We wrote ours; the test covers the FSM, and the surface is intentionally small.
