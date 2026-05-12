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
