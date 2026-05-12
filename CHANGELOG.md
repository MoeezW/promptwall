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
