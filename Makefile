# Single entry point for local development. Run `make help` for the list.
SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
API_CLIENT_DIR := frontend/packages/api-client

.PHONY: help dev down services install test test-backend test-live test-frontend lint lint-backend lint-frontend \
	gen-client check-client migrate infra-check images security secret-scan audit image-scan e2e e2e-install eval \
	seed seed-reset

help: ## List targets
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

dev: ## Start the whole stack (Postgres+pgvector, Redis, RustFS, Mailpit, API, worker, Beat, Studio, widget, demo host page)
	$(COMPOSE) up --build

down: ## Stop the stack
	$(COMPOSE) down

services: ## Start only Postgres, Redis and RustFS, for running the test suites on the host
	$(COMPOSE) up -d --wait postgres redis rustfs

install: ## Install backend and frontend dependencies
	cd backend && uv sync --frozen
	cd frontend && pnpm install --frozen-lockfile

test: test-backend test-frontend ## Run every test suite with the 100% coverage gate

test-backend: ## Backend tests against real Postgres and Redis (start them with `make services`)
	cd backend && uv run pytest

test-live: ## Live suite: real Docling on the sample files and the local Embedding Model (downloads models, skips with the reason without them unless LIVE_REQUIRE_MODELS=1; outside the coverage gate)
	cd backend && uv run --group pdf pytest -m live --no-cov -rs tests/live

test-frontend: ## Studio, widget and API client tests, then the embed loader's size budget
	cd frontend && pnpm test && pnpm check-embed-size

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

# The seed runs the API in a one-off container beside the running stack (`make dev`), with the
# repo's seed folder mounted at /seed. Files go to RustFS by its internal address. Set
# SEED_CREDENTIAL_PROVIDER (anthropic or openai) and SEED_CREDENTIAL_API_KEY (and optionally
# SEED_CREDENTIAL_MODEL) to answer with a real model instead of the demo one.
SEED_RUN = $(COMPOSE) run --rm --no-deps -v "$(CURDIR)/seed:/seed:ro" \
	-e OBJECT_STORE_PUBLIC_ENDPOINT_URL=http://rustfs:9000 \
	-e SEED_CREDENTIAL_PROVIDER -e SEED_CREDENTIAL_API_KEY -e SEED_CREDENTIAL_MODEL api

seed: ## Create the demo Organisation in the running stack and print its sign-in details (idempotent)
	$(SEED_RUN) sh -c "alembic upgrade head && python -m app.seed"

seed-reset: ## Erase the demo Organisation (only that one) and seed it again
	$(SEED_RUN) sh -c "alembic upgrade head && python -m app.seed --reset"

TF_ROOTS := $(sort $(dir $(wildcard infra/bootstrap/main.tf infra/modules/*/main.tf infra/envs/*/main.tf)))
IMAGE_TAG ?= local
TRIVY_SEVERITY ?= HIGH,CRITICAL
AUDIT_REQUIREMENTS ?= $(or $(RUNNER_TEMP),/tmp)/requirements-audit.txt

infra-check: ## Terraform fmt, validate, tflint, checkov and `terraform test` on the bootstrap, every module and environment, plus the deploy scripts' tests
	terraform fmt -check -recursive -diff infra
	infra/tests/backend.test.sh
	infra/tests/compose.test.sh
	scripts/deploy/tests/smoke.test.sh
	scripts/deploy/tests/deploy.test.sh
	scripts/deploy/tests/destroy.test.sh
	node --test --experimental-test-coverage --test-coverage-lines=100 --test-coverage-branches=100 --test-coverage-functions=100 \
		$(wildcard infra/modules/*/functions/*.test.mjs)
	scripts/ci/tests/plan-gate.test.sh
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

e2e: ## Start the stack, wait for health checks, seed the demo and run the Playwright suite against it
	$(COMPOSE) up -d --build --wait
	$(MAKE) seed
	cd frontend && pnpm e2e

eval: ## Guardrail attack evaluation suite (placeholder until ticket 08-07)
	@echo "Guardrail evaluation: no attack prompts yet. The suite arrives with ticket 08-07; passing as a placeholder."
