.PHONY: dev dev-down serve test lint format typecheck bench migrate clean help

CORE := packages/core

help:
	@echo "promptwall — make targets"
	@echo "  dev        Bring up Postgres + Jaeger via docker compose"
	@echo "  dev-down   Stop the dev stack (keeps volumes)"
	@echo "  serve      Run the proxy with uvicorn --reload on :8000"
	@echo "  test       Run the test suite"
	@echo "  lint       ruff check + ruff format --check"
	@echo "  format     ruff format (writes)"
	@echo "  typecheck  mypy --strict"
	@echo "  bench      Run the benchmark harness"
	@echo "  migrate    alembic upgrade head"
	@echo "  clean      docker compose down -v (DESTROYS volumes)"

dev:
	docker compose up -d postgres jaeger
	@echo ""
	@echo "Postgres:   postgresql://promptwall:promptwall@localhost:5432/promptwall"
	@echo "Jaeger UI:  http://localhost:16686"

dev-down:
	docker compose down

serve:
	cd $(CORE) && uv run python -m promptwall.main

test:
	cd $(CORE) && uv run pytest

lint:
	cd $(CORE) && uv run ruff check . && uv run ruff format --check .

format:
	cd $(CORE) && uv run ruff format . && uv run ruff check --fix .

typecheck:
	cd $(CORE) && uv run mypy src

bench:
	cd $(CORE) && uv run python -m promptwall.cli bench --n 1000

bench-smoke:
	cd $(CORE) && uv run python -m promptwall.cli bench --n 100

bench-with-ml:
	cd $(CORE) && uv run python -m promptwall.cli bench --n 1000 --with-ml

migrate:
	cd $(CORE) && uv run alembic upgrade head

clean:
	docker compose down -v
