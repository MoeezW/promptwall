# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Repository scaffolding: `packages/core` Python project with strict ruff
  + mypy, `docker-compose` dev stack (Postgres 16 + Jaeger 2.17), Alembic
  with an empty initial migration, Makefile targets, and pre-commit hooks.
- Proxy skeleton: `POST /v1/chat/completions` is an OpenAI-compatible
  passthrough. Every request is hashed (SHA-256), persisted to the
  `requests` table via async SQLAlchemy / psycopg3, and traced with OTLP
  spans (`proxy.chat.completions` with `provider.openai.forward` child).
  structlog emits JSON logs. Dedicated `main.py` entry point sets the
  Windows selector event-loop policy before uvicorn starts the loop, so
  psycopg's async mode works cross-platform.
- Detector framework: `Detector` Protocol with `DetectorResult` /
  `Span` / `ScanContext` DTOs, an async-aware three-state circuit
  breaker (closed | open | half_open) per detector, and a parallel
  runner built on `asyncio.TaskGroup` that enforces per-detector
  timeouts and sheds failing detectors. Hypothesis property tests
  cover the FSM and the runner's "every detector returns a result"
  invariant. Three concrete detectors: a curated regex pack for
  prompt injection (~30 patterns drawn from public corpora), a thin
  wrapper around Yelp's `detect-secrets` for credentials/tokens, and
  a Microsoft Presidio analyzer for PII with a custom Canadian
  Social Insurance Number recognizer (Luhn-validated). 98% coverage
  on the detector package.
- ML prompt-injection detector: `protectai/deberta-v3-base-prompt-injection-v2`
  via ONNX Runtime through `optimum`. Auto-downloads from HuggingFace
  and exports to ONNX on first construction (~50 s cold); subsequent
  loads reuse the HF cache (~1-2 s). Synchronous inference wrapped in
  `asyncio.to_thread`; 5-prompt warmup in the constructor.
  **Measured ~18 ms p99 on FP32**, well under the 25 ms budget — no
  int8 quantization needed for v0.1. `torch` came in as a transitive
  dep of `optimum 2.x`; runtime container will strip it (Phase 7).
- Reversible PII redaction: HMAC-SHA256-keyed tokens of the form
  `<PII:{TYPE}_{HMAC8}>` with a per-request 32-byte random salt. The
  redact / hydrate round-trip is the most important invariant in the
  codebase, verified by hypothesis. Look-alike tokens that the model
  hallucinates are left as-is — only tokens whose HMAC matches the
  per-request mapping are substituted.
- Policy engine: YAML schema (`promptwall.config`) loaded into Pydantic
  models, plus a `simpleeval`-backed expression evaluator
  (`promptwall.policy`) over detector results. Supports `and / or / not`,
  comparisons, attribute access (`pii.matched`, `injection_ml.score`);
  rejects function calls and arbitrary Python. Missing or degraded
  detectors fall the rule's action through to `degraded_action`
  (default `block`). Hypothesis property test confirms the evaluator
  never crashes on random rules + random detector results.
- Proxy now runs detectors → policy → maybe-redact → forward → maybe-hydrate
  → respond. End-to-end test verifies a prompt with a credit card is
  redacted before forwarding and re-hydrated in the response; blocked
  requests never touch the upstream provider.
- Default policy (`policies/default.yaml`): block on secrets, block on
  high-confidence regex injection, redact detected PII, allow otherwise.
  ML detector opt-in.
- Benchmark harness (`packages/core/benchmarks/`): direct-call (no proxy)
  evaluation across three corpora — a chained list of public
  prompt-injection sources (`Lakera/gandalf_ignore_instructions` first,
  then `xTRam1/safe-guard-prompt-injection`, then `deepset/prompt-injections`;
  HackAPrompt is gated on the Hub so we don't use it), JailbreakBench
  harmful behaviors, and `OpenAssistant/oasst1` benign. Reports
  per-detector detection rate / FPR with **95% bootstrap CIs (seed 42,
  10 000 resamples, percentile method)** plus p50/p99 latency.
  Reproducible via `make bench` (or `make bench-smoke` for n=100, or
  `make bench-with-ml`). Real numbers committed in
  `packages/core/benchmarks/results.md`. At n=500 with the ML detector
  enabled, the latest run hits **100% combined detection at 1.0% FPR on
  `Lakera/gandalf_ignore_instructions`** (a corpus aligned with the ML
  model's training distribution); the regex detector alone catches
  21.6% there. On a harder corpus with distributional shift
  (`deepset/prompt-injections`, which mixes in roleplay framing and
  urgency tactics the base model wasn't trained for), combined
  detection drops to ~46% — both numbers are real and committed.
  Honest, not heroic.
