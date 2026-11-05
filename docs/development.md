# Local development

Prerequisites: Docker with Compose v2, GNU Make, [uv](https://docs.astral.sh/uv/) and Node 22 with pnpm (via `corepack enable`). The infrastructure and security gates also need Terraform, TFLint, Checkov, gitleaks and Trivy; `scripts/ci/install-tools.sh terraform tflint checkov gitleaks trivy` installs the pinned, checksum-verified versions CI uses into `~/.local/bin`.

| Command | What it does |
|---|---|
| `make dev` | Builds and starts the whole stack: Postgres with pgvector, Redis, RustFS, Mailpit, the API, the Celery worker, Celery Beat and the Studio. |
| `make install` | Installs backend (`uv sync`) and frontend (`pnpm install`) dependencies on the host. |
| `make services` | Starts only Postgres and Redis, which the backend tests need. |
| `make test` | Backend and frontend tests, each failing below 100% line or branch coverage (ADR-0008). |
| `make lint` | ruff, `mypy --strict`, eslint and `tsc`. |
| `make gen-client` | Regenerates `frontend/packages/api-client` from the backend's OpenAPI schema. |
| `make check-client` | Fails if the committed API client differs from a fresh generation (CI runs this). |
| `make e2e-install` | Installs the Chromium build Playwright uses. |
| `make e2e` | Starts the stack with `docker compose up --wait`, then runs the Playwright suite (fixture checks and the Studio smoke test with axe). |
| `make infra-check` | `terraform fmt`, `validate`, `terraform test`, TFLint and Checkov over every module in `infra/modules` and every environment in `infra/envs`. |
| `make security` | gitleaks over the whole history (`secret-scan`), pip-audit and pnpm audit (`audit`), and a Trivy scan of the built images (`image-scan`). |
| `make images` | Builds the API image (also used by the worker and Beat) and the Studio image. |
| `make eval` | Guardrail evaluation suite; a passing placeholder until ticket 08-07. |

Once `make dev` is up:

- Studio: <http://localhost:5173> (the System status page shows API, database, Redis and worker health through the generated client)
- API: <http://localhost:8000/api/health>, OpenAPI docs at <http://localhost:8000/docs>
- Mailpit: <http://localhost:8025>
- RustFS console: <http://localhost:9001>

## Settings

Every backend service reads typed settings from the environment (`backend/app/core/settings.py`) and refuses to start when a required one is missing or invalid, naming the setting:

```
app.core.settings.SettingsError: Invalid service settings. DATABASE_URL: Field required
```

`docker-compose.yml` supplies the local values; `.env.example` lists them.

## Telemetry and logs

The API, worker and Beat are traced with OpenTelemetry through the Logfire SDK (`backend/app/core/telemetry.py`). FastAPI requests, SQLAlchemy queries, Celery tasks (from the request that queues them through to the worker that runs them) and outbound `httpx` calls are instrumented.

- **Exporter.** With `LOGFIRE_TOKEN` set, spans go to Logfire (`LOGFIRE_BASE_URL` is only needed for a self-hosted Logfire). Without it they are written to stdout, one JSON object per span.
- **Scrubbing.** Every exporter receives spans after Logfire's scrubbing processor, extended for this project. Values under Message-carrying field names (`content`, `message`, `messages`, `prompt`, and `input`, where validation errors echo a request back) are redacted, as are cookies, `Authorization` and API-key headers, and secret-like attributes. Request headers are captured, so these are redacted rather than simply absent. A log message whose template formats a scrubbed value is exported as the bare template.
- **Logs.** Every service writes JSON lines to stdout: `timestamp`, `level`, `logger`, `message`, `service` (`api`, `worker`, `beat` or `migrations`), any `extra` fields, `exception` when there is one, and `trace_id`/`span_id` inside a traced operation. Extra fields with sensitive names, and the task arguments and results Celery logs, are written as `[Redacted]`.
- **Entrypoints.** The API runs as `python -m app.serve`, so uvicorn's own lines are JSON too. Celery runs with `--quiet` so it skips its text banner; the one line Celery still prints outside logging is its `worker: Warm shutdown (MainProcess)` notice on SIGTERM.

## Tests

Backend tests run against real Postgres and Redis. With `make services` running they use the `studio_test` database and Redis database 15; override with `TEST_DATABASE_URL` and `TEST_REDIS_URL`.

## End-to-end tests

Playwright lives in `frontend/e2e`, and its config is `frontend/playwright.config.ts`. It has two projects:

- `harness` checks the shared fixtures against an in-process fake Studio, so it runs without the stack (`pnpm e2e:harness`).
- `studio` runs against the stack at `E2E_BASE_URL` (default <http://localhost:5173>).

Specs import `test` and `expect` from `frontend/e2e/fixtures`, not from `@playwright/test`. That gives every spec these fixtures:

| Fixture | What it does |
|---|---|
| `stack` (automatic, once per worker) | Waits until the Studio loads and, through its `/api` proxy, the API reports the database and Redis ok and a worker answers the health task. It gives up after `E2E_STACK_TIMEOUT_MS` (default 180 s) and names the failing check. |
| `member` | A new, unique Member (name, email, password, Organisation name) who has not signed up yet. |
| `signedInPage` | A page signed in as `member`, who has just signed up and so owns a new Organisation. It uses the auth API directly; `signUp`, `signIn` and `signInAs` in `fixtures/auth.ts` do the same for other Members. The routes it calls are the ones ticket 01-04 implements. |
| `makeAxeBuilder` | An axe scan of the page limited to WCAG 2.2 AA rules. |

To use a Chromium that is already installed instead of Playwright's download, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`.

## CI workflows

| Workflow | Runs |
|---|---|
| `backend.yml` | ruff, `mypy --strict`, pytest with the coverage gate and the Alembic round trip |
| `frontend.yml` | eslint, `tsc`, Vitest with the coverage gate, build, API client drift check |
| `e2e.yml` | `make e2e`: compose stack, health checks, Playwright with axe; uploads the HTML report |
| `security.yml` | gitleaks, pip-audit, pnpm audit, Trivy on the built images; also weekly |
| `infra.yml` | `make infra-check`; `terraform plan` on pull requests only once the `AWS_DEPLOY_ROLE_ARN` secret exists |
| `deploy.yml` | Builds the images on every push. Pushing to ECR (on `main`) and the manual `apply` / `destroy` of `envs/demo` run only when `AWS_DEPLOY_ROLE_ARN` is set; otherwise those steps are skipped with a notice. |
| `guardrails-eval.yml` | `make eval`, a passing placeholder until ticket 08-07 |
