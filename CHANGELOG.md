# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — 0.1.0

The first release. promptwall is an OpenAI-compatible reverse proxy that
scans inputs against a configurable safety policy and forwards the rest
to the real provider. What lands in 0.1.0:

### Proxy and provider

- `POST /v1/chat/completions` is an OpenAI-compatible passthrough that
  runs detectors → policy → maybe-redact → forward → maybe-hydrate before
  responding. Every request is hashed (SHA-256) and persisted to the
  `requests` table; the request envelope, detector results, and policy
  decision land in three columns of one row per request.
- `providers/openai.py` is a pooled `httpx.AsyncClient` adapter; the
  proxy never invents the upstream URL or auth. Streaming (`stream=true`)
  is forwarded as SSE pass-through and not scanned in v0.1.
- A dedicated `main.py` entry point sets `WindowsSelectorEventLoopPolicy`
  before uvicorn starts the loop so `psycopg`'s async mode works on
  Windows as well as Linux.

### Detectors

- `Detector` Protocol with `DetectorResult` / `Span` / `ScanContext`
  DTOs in `detectors/base.py`.
- Three-state circuit breaker (closed | open | half_open) per detector
  with configurable failure threshold and recovery window. State
  transitions are covered by a hypothesis property test.
- Parallel runner built on `asyncio.TaskGroup` that enforces a
  per-detector timeout, converts timeouts and exceptions into synthetic
  degraded results, and trips the relevant breaker. A second property
  test verifies "every detector returns a result, even when peers fail."
- Four concrete detectors:
  - `injection_regex` — a curated pack of ~30 prompt-injection patterns
    drawn from public corpora.
  - `secrets` — thin wrapper around Yelp's `detect-secrets` with span
    extraction for the dashboard.
  - `pii` — Microsoft Presidio's `AnalyzerEngine` with the default
    recognizers plus a custom Luhn-validated Canadian SIN recognizer.
  - `injection_ml` — `protectai/deberta-v3-base-prompt-injection-v2`
    auto-exported to ONNX through `optimum`. Synchronous inference is
    wrapped in `asyncio.to_thread`; a 5-prompt warmup runs at startup
    so the first real request isn't a 500 ms outlier. **Measured
    ~18 ms p99 on FP32**, well inside the 25 ms budget — no INT8
    quantization needed for v0.1.

### Policy engine

- YAML policy schema in `promptwall.config`, validated through Pydantic.
- `simpleeval`-backed expression evaluator over detector results
  (`and / or / not`, comparisons, dotted access — no function calls, no
  arbitrary Python). When a referenced detector is missing or degraded
  the rule falls through to `degraded_action` (default `block`).
- A hypothesis property test confirms the evaluator never crashes on
  random rules + random detector results.

### Reversible PII redaction

- Per-request 32-byte cryptographic salt; PII spans are replaced with
  HMAC-SHA256-keyed tokens of the form `<PII:{TYPE}_{HMAC8}>`.
- Hydration on the response side substitutes back **only** the tokens
  whose HMAC matches the per-request mapping. Look-alike tokens the
  model may hallucinate are left as-is.
- The `hydrate(redact(text)) == text` round-trip is the most important
  invariant in the codebase and is verified by a hypothesis test on
  every commit.

### Benchmark harness

- Direct-call (no provider spend) evaluation across three corpora:
  a chained list of public prompt-injection sources
  (`Lakera/gandalf_ignore_instructions` first, then
  `xTRam1/safe-guard-prompt-injection`, then `deepset/prompt-injections`;
  HackAPrompt is Hub-gated so we skip it), JailbreakBench harmful
  behaviors (reported for completeness — these are direct harmful-content
  asks, not injection patterns), and `OpenAssistant/oasst1` first-turn
  English prompts as the benign baseline.
- Reports per-detector detection rate / FPR with **95% bootstrap CIs
  (seed 42, 10 000 percentile resamples)** plus p50 and p99 latency.
- Reproducible via `make bench` (n=1000), `make bench-smoke` (n=100,
  for CI), and `make bench-with-ml` (engages the ML detector).
- Real numbers committed in `packages/core/benchmarks/results.md`. With
  the ML detector enabled at n=500, the latest run hits **100% combined
  detection at 1.0% FPR on `Lakera/gandalf_ignore_instructions`**.
  The regex detector alone catches 21.6% on the same corpus. Honest,
  not heroic.

### Dashboard

- Next.js 16 App Router + Tailwind + Recharts at `packages/dashboard/`.
- Two pages: `/requests` (paginated table with allow / redact / block
  action badges) and `/requests/[id]` (detail view with the per-detector
  score bar chart, full decision tree, and a deep link to the Jaeger
  trace).
- Server-component fetches; no client-side state library.
- Read API at `GET /api/requests` and `GET /api/requests/{id}` mounted
  on the same FastAPI app as the proxy, so a single uvicorn serves
  both. Next.js `rewrites` proxy `/api/*` to it in dev.

### Persistence and observability

- One SQLModel table — `requests` — with `request_hash`, `model`,
  `latency_ms`, `status`, `created_at`, plus `detector_results` and
  `policy_decision` JSON columns. Request and response *bodies* are
  not logged in v0.1; persisting them behind a config flag is on the
  roadmap.
- Alembic migrations for the schema; `make migrate` applies them.
- Structured JSON logs via structlog. Every line carries `event=...`
  and `request_id` (the request hash prefix) where applicable.
- One OTel span tree per request — `proxy.chat.completions` with
  `detectors.scan` and (on allow/redact) `provider.openai.forward`
  children. OTLP exporter ships them to the Jaeger instance brought
  up by `make dev`.

### Packaging, CI, and docs

- Multi-stage `packages/core/Dockerfile` that strips `torch` from the
  runtime stage — ONNX Runtime is enough for inference (see
  [ADR-0004](./docs/adrs/0004-onnx-runtime-over-torch.md)). Target
  image size under 1 GB.
- `docker compose --profile full up --build` runs the full stack
  (postgres + jaeger + core + dashboard) from a clean clone.
- GitHub Actions: `ci.yml` (lint, typecheck, test with the 80 % coverage
  gate, dashboard build, container build) and `bench.yml` (n=100 smoke
  on PR — catches structural regressions in the harness).
- Four ADRs in `docs/adrs/` covering the language choice, the redaction
  scheme, the structured-concurrency runner, and the ONNX-over-torch
  call. `docs/ARCHITECTURE.md` has Mermaid sequence diagrams for the
  happy / blocked / redacted paths.
- `examples/openai_sdk_dropin.py` plus curl examples for each path.
- `CONTRIBUTING.md` and issue templates.
- Apache-2.0 `LICENSE`.

### Known limitations

- Streaming responses are not scanned (SSE pass-through only).
- Authentication is not enforced — v0.1 expects to live behind a
  trusted edge.
- Circuit breaker state is per-process by design; a multi-instance
  deployment has per-pod breakers. This is correct for the failure
  mode it targets, not a gap in disguise.
- The ML detector's performance is sensitive to training-distribution
  alignment: 100 % on `Lakera/gandalf_ignore_instructions`, ~46 % on
  `deepset/prompt-injections`. Both numbers are committed.
