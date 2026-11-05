# Single entry point for local development. Run `make help` for the list.
SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
API_CLIENT_DIR := frontend/packages/api-client

.PHONY: help dev down services install test test-backend test-frontend lint lint-backend lint-frontend \
	gen-client check-client migrate infra-check images security secret-scan audit image-scan e2e e2e-install eval

help: ## List targets
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

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

TF_ROOTS := $(sort $(dir $(wildcard infra/modules/*/main.tf infra/envs/*/main.tf)))
IMAGE_TAG ?= local
TRIVY_SEVERITY ?= HIGH,CRITICAL
AUDIT_REQUIREMENTS ?= $(or $(RUNNER_TEMP),/tmp)/requirements-audit.txt

infra-check: ## Terraform fmt, validate, tflint, checkov and `terraform test` on every module and environment
	terraform fmt -check -recursive -diff infra
	@set -e; for root in $(TF_ROOTS); do \
		echo "== $$root"; \
		terraform -chdir=$$root init -backend=false -input=false -no-color >/dev/null; \
		terraform -chdir=$$root validate -no-color; \
		terraform -chdir=$$root test -no-color; \
	done
	cd infra && tflint --init && tflint --recursive --config "$$PWD/.tflint.hcl"
	cd infra && checkov --config-file .checkov.yaml

images: ## Build the API (also used by the worker and Beat) and Studio images
	docker build -t rag-agent-studio/api:$(IMAGE_TAG) backend
	docker build -t rag-agent-studio/studio:$(IMAGE_TAG) frontend

security: secret-scan audit image-scan ## Every security gate: gitleaks, pip-audit, pnpm audit and Trivy

secret-scan: ## gitleaks over the whole git history
	gitleaks git --redact --no-banner .

audit: ## pip-audit on the locked backend dependencies and pnpm audit on the frontend workspace
	cd backend && uv export --frozen --no-emit-project --quiet -o "$(AUDIT_REQUIREMENTS)" \
		&& uvx pip-audit==2.10.0 --strict --disable-pip --require-hashes -r "$(AUDIT_REQUIREMENTS)"
	cd frontend && pnpm audit --audit-level low

image-scan: images ## Trivy scan of the built images; fails on any fixable HIGH or CRITICAL vulnerability
	trivy image --exit-code 1 --ignore-unfixed --severity $(TRIVY_SEVERITY) rag-agent-studio/api:$(IMAGE_TAG)
	trivy image --exit-code 1 --ignore-unfixed --severity $(TRIVY_SEVERITY) rag-agent-studio/studio:$(IMAGE_TAG)

e2e-install: ## Install the Playwright browser the end-to-end suite uses
	cd frontend && pnpm exec playwright install --with-deps chromium

e2e: ## Start the stack, wait for health checks and run the Playwright suite against it
	$(COMPOSE) up -d --build --wait
	cd frontend && pnpm e2e

eval: ## Guardrail attack evaluation suite (placeholder until ticket 08-07)
	@echo "Guardrail evaluation: no attack prompts yet. The suite arrives with ticket 08-07; passing as a placeholder."
