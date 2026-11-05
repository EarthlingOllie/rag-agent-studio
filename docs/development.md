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
| `make e2e` | Starts the stack with `docker compose up --wait`, then runs the Playwright suite (fixture checks and the Studio smoke and auth tests with axe). |
| `make infra-check` | `terraform fmt`, `validate`, `terraform test`, TFLint (with the AWS ruleset) and Checkov over `infra/bootstrap`, every module in `infra/modules` and every environment in `infra/envs`, plus the S3 backend check (`infra/tests/backend.test.sh`) and the plan-gate tests (`scripts/ci/tests/plan-gate.test.sh`). No AWS account is needed: `terraform test` uses mocked providers. |
| `make security` | gitleaks over the whole history (`secret-scan`), pip-audit and pnpm audit (`audit`), and a Trivy scan of the built images (`image-scan`). |
| `make images` | Builds the API image (also used by the worker and Beat) and the Studio image. |
| `make eval` | Guardrail evaluation suite; a passing placeholder until ticket 08-07. |

Once `make dev` is up:

- Studio: <http://localhost:5173> (sign up there to create an Organisation; <http://localhost:5173/status> shows API, database, Redis and worker health through the generated client)
- API: <http://localhost:8000/api/health>, OpenAPI docs at <http://localhost:8000/docs>
- Mailpit: <http://localhost:8025>
- RustFS console: <http://localhost:9001>

## Settings

Every backend service reads typed settings from the environment (`backend/app/core/settings.py`) and refuses to start when a required one is missing or invalid, naming the setting:

```
app.core.settings.SettingsError: Invalid service settings. DATABASE_URL: Field required
```

`docker-compose.yml` supplies the local values; `.env.example` lists them.

## Sign-in and tenancy

- **Sessions.** Signing up or in starts a server-side session in Redis (key `session:<sha256 of the token>`, value the Member's ID, TTL `SESSION_TTL_SECONDS`, default 14 days). The browser holds only the opaque token, in the `studio_session` cookie (`HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`). Every sign-in or sign-up issues a new token and ends the session the browser had before. Signing out deletes the session in Redis and clears the cookie. Browsers accept `Secure` cookies from `http://localhost`, so local development needs no TLS.
- **Passwords** are hashed with argon2id (`argon2-cffi` defaults, RFC 9106). Sign-in answers `401 {"detail": "Email or password is incorrect"}` for an unknown email and a wrong password alike, and verifies against a dummy hash when the email is unknown so the timing matches too.
- **Sign-in protection** (`app/auth/throttle.py`). Failed sign-ins are counted in Redis per account (key `sign-in-failures:account:<sha256 of the normalised email>`) and per IP address (`sign-in-failures:ip:<ip>`). Unknown emails are counted exactly like registered ones. After `SIGN_IN_ACCOUNT_DELAY_AFTER_FAILURES` (3) failures for an account, or `SIGN_IN_IP_DELAY_AFTER_FAILURES` (20) from an IP, the next attempt must wait 1 second after the last failure, then 2, 4… up to `SIGN_IN_DELAY_MAX_SECONDS` (30). After `SIGN_IN_ACCOUNT_LOCKOUT_AFTER_FAILURES` (10) or `SIGN_IN_IP_LOCKOUT_AFTER_FAILURES` (100) sign-in is locked out for `SIGN_IN_LOCKOUT_SECONDS` (900). An attempt that must wait is refused before the password is checked, with `429 {"detail": "Too many failed sign-in attempts", "locked": <bool>, "retry_after_seconds": <n>}` and a `Retry-After` header; refused attempts aren't counted, so waiting always works. A successful sign-in clears the account's counter (not the IP's). A counter is forgotten `SIGN_IN_LOCKOUT_SECONDS` after its last failure. Times come from the `Clock` port (`app/core/clock.py`; tests use the `clock` fixture, a `ControllableClock`), so Redis expiry only garbage-collects. Each Lockout is logged (`Sign-in locked out`) and, when the email belongs to a Member, recorded as a `member.locked_out` Audit Event in each of their Organisations (actor none, target the Member, `after` holds scope, IP, failures and `locked_until`).
- **Client IP behind proxies.** The API takes the IP from uvicorn, which trusts `X-Forwarded-For` only from the addresses in `FORWARDED_ALLOW_IPS` (default `127.0.0.1`). Compose sets `*` and the Studio dev proxy sends the header, so local limits count per browser. A deployment must list its load balancers there; otherwise every visitor shares the load balancer's IP counter.
- **Tenancy.** `organisations` and `members` are platform-level tables. Every other table carries a non-null `organisation_id`, and a test fails if one doesn't. Tenant data is read through `app/tenancy/repository.py` functions that take an `OrganisationScope`. Routes get one from the `Scope` dependency (`app/tenancy/policy.py`), which reads `{organisation_id}` from the path and answers 404 when the Member doesn't belong to it, exactly as for an Organisation that doesn't exist.
- **Isolation test.** `backend/tests/integration/test_tenant_isolation.py` lists every Organisation-scoped route in `ORGANISATION_SCOPED_ROUTES` and checks that another tenant's Member gets 404 and a signed-out visitor 401. A guard test fails when the OpenAPI document has an `{organisation_id}` route that isn't listed, so adding a route means adding it there (with a `prepare` step if it needs resources inside the Organisation).
- **Backend test fixtures** (`backend/tests/conftest.py`): `client` (HTTPS base URL, so the `Secure` cookie round-trips), `new_client` (another browser on the same app), `tenant_factory` (signs a new Member up in a fresh client, so they own a new Organisation), `owner` and `clock` (a `ControllableClock` installed on the app). Each test starts with no sign-in failure counters. The test database is migrated to head once per run.

## Audit Events

- **Recording.** `app.audit.record(session, organisation_id=…, actor_id=…, action=…, target=AuditTarget(type, id), before=…, after=…)` adds an Audit Event to the caller's transaction, so the change and its event commit or roll back together. `actor_id` is `None` for events no Member caused. Actions are dotted names (`organisation.created`, the first one, is recorded at sign-up). Keys matching a secret-like pattern (`password`, `secret`, `token`, `api_key`, `credential`, `private_key`, `authorization`, `cookie`, `session`, `recovery_codes`, …) have their values replaced by `[Redacted]` at any depth before anything is stored.
- **Append-only.** Migration `0003_audit` adds triggers that refuse `UPDATE`, `DELETE` and `TRUNCATE` on `audit_events`.
- **Reading.** `GET /api/organisations/{organisation_id}/audit-events` (filters `actor_id`, `action`, `start` inclusive, `end` exclusive, both with a time zone; `page`, `page_size` up to 100; newest first) and `GET …/audit-events/facets` (the actors and actions present, for filter menus). Both are Owner-only through the `OwnerScope` dependency (`app/tenancy/policy.py`): an Editor gets `403 {"detail": "Only Owners can do this"}`, another tenant's Member 404.
- **Studio.** Organisation settings has a General tab and, for Owners only, an Audit tab (`/organisations/$organisationId/settings/audit`). Its date filters are whole UTC days, both inclusive.

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
| `infra.yml` | `make infra-check`. On pull requests, `plan-gate` (`scripts/ci/plan-gate.sh`) decides whether `terraform plan (demo)` runs: only when the `AWS_DEPLOY_ROLE_ARN` secret exists and the pull request touches `infra/` or this workflow. Otherwise the plan job shows as skipped, with a notice saying why. When it runs, the plan is posted as a pull request comment. Setting it up: [infra-bootstrap.md](infra-bootstrap.md). |
| `deploy.yml` | Builds the images on every push. Pushing to ECR (on `main`) and the manual `apply` / `destroy` of `envs/demo` run only when `AWS_DEPLOY_ROLE_ARN` is set; otherwise those steps are skipped with a notice. `apply` / `destroy` initialise the S3 backend from the `TF_STATE_BUCKET` variable. |
| `guardrails-eval.yml` | `make eval`, a passing placeholder until ticket 08-07 |
