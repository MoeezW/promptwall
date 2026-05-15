# Contributing to promptwall

Thanks for the interest. A few notes that will save us both time.

## Before opening a PR

- Run `make lint typecheck test` locally. CI runs the same gates and will block on coverage under 80%.
- If you're changing the policy YAML schema, the `DetectorResult` shape, or a database column, open an issue first — these are versioned surfaces and changes need an ADR.
- One logical change per commit. Conventional commit prefixes (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `perf:`).

## Development setup

```bash
make dev        # postgres + jaeger via docker compose
make migrate    # alembic upgrade head
make serve      # uvicorn on :8000 (proxy + read API)
make dashboard  # next.js dev server on :3000
make test       # full test suite
make bench      # benchmark harness against public corpora
```

Python is managed with [`uv`](https://docs.astral.sh/uv/); the dashboard uses [`pnpm`](https://pnpm.io/). Neither is optional.

## Adding a detector

1. Create a new file in `packages/core/src/promptwall/detectors/`.
2. Implement the `Detector` Protocol from `detectors/base.py`. Return a `DetectorResult` with `score ∈ [0.0, 1.0]`, `matched`, and any `spans`.
3. Add a unit test file with at least five positive and five negative cases plus a latency assertion.
4. Register the detector in `proxy.py::_build_detectors` and document its config in `policies/default.yaml`.
5. If the detector loads model weights, do it once in `__init__` or `lifespan` — never per request.

Detectors must not raise on malformed input. Return a `DetectorResult` with `score=0.0, matched=False, metadata={"error": "..."}` and let the circuit breaker handle the rest.

## ADRs

Non-trivial decisions get an ADR in `docs/adrs/`. Use the existing format: Context, Decision, Consequences, Rejected alternatives. Keep them under 500 words; prose, not bullet lists.

## What we don't accept

- New top-level directories without an ADR.
- New runtime dependencies without an issue justifying them (license, last release date, transitive dep count).
- Catch-all `except Exception` or bare `except:`. The CLAUDE.md anti-slop rules in the project root apply to PR review too.
- AI-generated PR descriptions that don't say what changed and why.
