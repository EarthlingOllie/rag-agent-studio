# Single entry point for local development. Run `make help` for the list.
SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
API_CLIENT_DIR := frontend/packages/api-client

.PHONY: help dev down services install test test-backend test-live test-frontend lint lint-backend lint-frontend \
	gen-client check-client migrate infra-check images security secret-scan audit image-scan e2e e2e-install eval eval-live \
	seed seed-reset link-check

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

# TEST_WORKERS=N runs the backend suite on N pytest-xdist workers (`auto`: one per CPU), each
# with its own Postgres database (studio_test_gwN, created on first use) and Redis database.
# Unset runs serially against studio_test and Redis database 15, as before.
TEST_WORKERS ?=

test-backend: ## Backend tests against real Postgres and Redis (start them with `make services`); TEST_WORKERS=N runs them in parallel
	cd backend && uv run pytest $(if $(TEST_WORKERS),-n $(TEST_WORKERS))

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

link-check: ## Check that every relative link (and its #anchor) in the Markdown git tracks resolves; offline, with the checker's tests at 100% coverage
	node --test --experimental-test-coverage --test-coverage-lines=100 --test-coverage-branches=100 --test-coverage-functions=100 \
		scripts/ci/tests/links.test.mjs
	node scripts/ci/link-check.mjs

TF_ROOTS := $(sort $(dir $(wildcard infra/bootstrap/main.tf infra/modules/*/main.tf infra/envs/*/main.tf)))
IMAGE_TAG ?= local
# Empty builds for this machine's architecture. The deploy workflow sets linux/arm64: the ECS tasks run on ARM64.
IMAGE_PLATFORM ?=
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

images: ## Build the API (also used by the worker and Beat) and Studio images; IMAGE_PLATFORM=linux/arm64 builds for Fargate
	docker build $(if $(IMAGE_PLATFORM),--platform $(IMAGE_PLATFORM)) -t rag-agent-studio/api:$(IMAGE_TAG) backend
	docker build $(if $(IMAGE_PLATFORM),--platform $(IMAGE_PLATFORM)) -t rag-agent-studio/studio:$(IMAGE_TAG) frontend

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

# The attack evaluation suite (backend/evals/attack_suite.json) through the real Guardrail
# pipeline with the local classifier (fetched from Hugging Face on first use). Reports go to
# EVAL_OUT as attack-eval-report.json and attack-eval-report.md.
EVAL_OUT ?= $(CURDIR)/backend/eval-report
EVAL_MIN_PASS_RATE ?= 0.85

eval: ## Guardrail attack evaluation suite against the naive mocked model; fails on any unexpected outcome
	cd backend && uv run python -m app.evals --mode mocked --out "$(EVAL_OUT)"

eval-live: ## The suite against a real model (EVAL_PROVIDER, EVAL_MODEL, EVAL_API_KEY); fails below EVAL_MIN_PASS_RATE
	cd backend && uv run python -m app.evals --mode live --provider "$(EVAL_PROVIDER)" \
		--model "$(EVAL_MODEL)" --min-pass-rate "$(EVAL_MIN_PASS_RATE)" --out "$(EVAL_OUT)"
