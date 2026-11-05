# Single entry point for local development. Run `make help` for the list.
SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
API_CLIENT_DIR := frontend/packages/api-client

.PHONY: help dev down services install test test-backend test-frontend lint lint-backend lint-frontend \
	gen-client check-client migrate

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

dev: ## Start the whole stack (Postgres+pgvector, Redis, RustFS, Mailpit, API, worker, Beat, Studio)
	$(COMPOSE) up --build

down: ## Stop the stack
	$(COMPOSE) down

services: ## Start only Postgres and Redis, for running the test suites on the host
	$(COMPOSE) up -d --wait postgres redis

install: ## Install backend and frontend dependencies
	cd backend && uv sync --frozen
	cd frontend && pnpm install --frozen-lockfile

test: test-backend test-frontend ## Run every test suite with the 100% coverage gate

test-backend: ## Backend tests against real Postgres and Redis (start them with `make services`)
	cd backend && uv run pytest

test-frontend: ## Studio and API client tests
	cd frontend && pnpm test

lint: lint-backend lint-frontend ## Lint and type-check backend and frontend

lint-backend:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy

lint-frontend:
	cd frontend && pnpm lint && pnpm typecheck

gen-client: ## Regenerate the TypeScript API client from the backend's OpenAPI schema
	cd backend && uv run python -m app.openapi ../$(API_CLIENT_DIR)/openapi.json
	cd frontend && pnpm gen-client

check-client: gen-client ## Fail if the committed API client differs from a fresh generation
	@if [ -n "$$(git status --porcelain -- $(API_CLIENT_DIR))" ]; then \
		git status --short -- $(API_CLIENT_DIR); git --no-pager diff -- $(API_CLIENT_DIR); \
		echo "The committed API client is out of date. Run 'make gen-client' and commit the result." >&2; \
		exit 1; \
	fi; echo "API client is up to date."

migrate: ## Apply database migrations to the running stack
	$(COMPOSE) exec api alembic upgrade head
