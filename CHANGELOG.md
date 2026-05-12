# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Repository scaffolding: `packages/core` Python project with strict ruff
  + mypy, `docker-compose` dev stack (Postgres 16 + Jaeger 2.17), Alembic
  with an empty initial migration, Makefile targets, and pre-commit hooks.
