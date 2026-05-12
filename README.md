# promptwall

> A self-hosted LLM safety gateway. Drop it in front of any provider with a one-line client change.

**Status:** under construction.

promptwall sits between your application and an LLM provider as a drop-in OpenAI-compatible proxy. Every request and response is scanned against a YAML-driven policy — prompt injection, PII, secrets, topic violations, toxicity — with detectors running concurrently under per-detector latency budgets and circuit breakers, so a single slow model never drags the request path. Detected PII is replaced with reversible HMAC-keyed tokens before forwarding, then re-hydrated on the way back, preserving completion quality end-to-end. Every decision is logged with an OpenTelemetry trace, and every release is benchmarked against HackAPrompt, JailbreakBench, and OpenAssistant with 95% bootstrap confidence intervals.

## Development

```bash
make dev        # bring up Postgres + Jaeger
make test       # run the test suite
make lint       # ruff check + ruff format --check
make typecheck  # mypy --strict
make bench      # run the benchmark harness
make migrate    # apply Alembic migrations
```

## License

Apache-2.0. See [LICENSE](./LICENSE).
