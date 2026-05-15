# ADR 0001 — Python (not TypeScript) for the core service

**Status:** Accepted
**Date:** 2026-04-22

## Context

The dashboard is Next.js, so a TypeScript core was on the table. A single-language repo is genuinely nicer to maintain: one toolchain, one set of types, one CI matrix. The case against came from the surrounding ecosystem.

Most of what this project needs already exists, in Python:

- **Microsoft Presidio** for PII. The de-facto open-source choice with ~50 entity recognizers and a documented extension point we use for the Canadian SIN recognizer.
- **`detect-secrets`** (Yelp) for credentials and tokens. Battle-tested ruleset, Apache-2.0.
- **`optimum` + ONNX Runtime** for ML inference. The `optimum-cli export onnx` path is what `protectai/deberta-v3-base-prompt-injection-v2` is documented against.
- **`datasets`** for HackAPrompt / Lakera Gandalf / JailbreakBench loaders.
- **`hypothesis`** for property tests on the policy evaluator and redaction round-trip.

The Node equivalents fragment into half-built libraries: `@xenova/transformers` for ONNX exists but Presidio doesn't, `secretlint` is close but not equivalent, and the HuggingFace dataset story is poor. We'd be porting half the toolchain ourselves before writing a line of business logic.

## Decision

The core service is Python 3.11+ using FastAPI, asyncio, and SQLModel. TypeScript is confined to the dashboard.

## Consequences

**Good:**

- Direct use of Presidio, detect-secrets, optimum, datasets, and hypothesis without writing adapters.
- `asyncio.TaskGroup` (3.11+) gives us structured concurrency for detector orchestration, which is the operational-maturity differentiator (see [ADR 0003](./0003-structured-concurrency-with-circuit-breakers.md)).
- `mypy --strict` enforces a Pydantic-typed API surface that's nearly as strong as TS at the boundaries.

**Tradeoffs:**

- Two languages in the repo, two CI lanes (uv + pnpm), two lint configurations.
- The dashboard can't share Pydantic types directly; the API exposes JSON and the dashboard types it independently. Acceptable for a small surface (two routes); revisit if the API grows.

## Rejected alternatives

- **TypeScript + `@xenova/transformers` everywhere.** Would have required reimplementing Presidio's recognizers in TS, building a HuggingFace dataset loader, and writing a hypothesis-equivalent property tester. Several weeks of yak-shave before a single detection.
- **Rust + ONNX Runtime bindings.** Best runtime profile but the ecosystem is even thinner — no Presidio, no Yelp's `detect-secrets`, no `datasets`. A research project, not a one-week portfolio piece.
- **Go.** Fast and concise but the AI/ML library landscape on Go is the weakest of the three.
