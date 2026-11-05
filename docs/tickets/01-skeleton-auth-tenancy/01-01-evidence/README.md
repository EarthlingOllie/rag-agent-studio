# Evidence: ticket 01-01, walking skeleton

Branch `ticket/01-01-walking-skeleton`. Logs marked "fresh clone" were produced from a new `git clone` of the branch at commit `820d786` (the last code change), with Postgres+pgvector and Redis from `make services`. Commands are at the top of each log, and each ends with its exit code.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | One command starts Postgres with pgvector, Redis, RustFS, Mailpit, the API, the worker, Beat and the Studio | `docker-compose.yml`, `make dev` (`docker compose up --build`). [compose-stack.log](compose-stack.log) shows all eight services up and healthy. It also shows the API, worker and Studio-proxy health responses, Mailpit and RustFS answering 200, pgvector 0.8.1 installed, and Beat sending the scheduled health task that the worker then completes. |
| 2 | Make targets exist for dev, test, lint and client generation | `Makefile`. [make-targets.log](make-targets.log) lists `dev`, `test`, `lint`, `gen-client` and `check-client`, plus `services`, `install`, `test-backend`, `test-frontend` and `migrate`. [lint.log](lint.log), [backend-tests.log](backend-tests.log), [frontend-tests.log](frontend-tests.log) and [client-drift.log](client-drift.log) show them running. |
| 3 | Settings are typed and validated at startup; a missing required setting fails fast with a clear message | `backend/app/core/settings.py`: a Pydantic Settings model, loaded in the API lifespan and in the worker/Beat entrypoint. Tests: `tests/integration/test_settings.py` (missing `DATABASE_URL`; invalid `REDIS_URL` and timeout) and `test_worker_entrypoint.py::test_worker_entrypoint_fails_fast_naming_a_missing_setting`. Real containers: [settings-fail-fast.log](settings-fail-fast.log) shows `SettingsError: Invalid service settings. DATABASE_URL: Field required`, after which uvicorn exits. |
| 4 | A Studio page shows API health through the generated client, and a Celery health task completes a round trip | The Studio System status page (`frontend/apps/studio/src/status/`) calls `/api/health` and `/api/health/worker` through `@studio/api-client`, the `openapi-fetch` client typed by `schema.gen.ts` generated from the backend's OpenAPI. Screenshots from the running stack: [studio-status-page.png](studio-status-page.png) (all OK, "Worker replied: pong") and [studio-status-page-worker-stopped.png](studio-status-page-worker-stopped.png) (worker stopped, so the Worker row shows Unavailable). The Celery round trip is tested at the task seam: `test_worker_health.py` runs eager, then through a real Redis broker with an in-process worker, then with no worker (503). The real worker log is in [compose-stack.log](compose-stack.log). |
| 5 | Alembic is configured, with an upgrade-to-head / downgrade-to-base round-trip test | `backend/alembic.ini`, `backend/migrations/` (async env using validated settings; `0001` enables pgvector). Test: `tests/integration/test_migrations.py` goes head → base → head, checking the revision and the extension each time. [alembic-round-trip.log](alembic-round-trip.log) has the test plus the same round trip run by hand inside the API container. |
| 6 | Backend and frontend CI workflows run lint, type checks and tests, and fail below 100% line or branch coverage | `.github/workflows/backend.yml` runs ruff, `mypy --strict` and pytest with `fail_under = 100` and branch coverage (`pyproject.toml`). `.github/workflows/frontend.yml` runs eslint, tsc, Vitest with all v8 thresholds at 100 (`vitest.config.ts`) and the build. [ci-runs.log](ci-runs.log) has real GitHub Actions runs on this branch: both green on `820d786`, and backend red on `9339730`. [coverage-gate-demo.log](coverage-gate-demo.log) shows each gate failing when one test is removed: backend 98.51% fails with exit 1, frontend 96.87% branches fails with exit 2. |
| 7 | CI fails when the committed API client differs from a fresh generation | The `api-client-drift` job in `frontend.yml` runs `make check-client`. That target regenerates `openapi.json` and `schema.gen.ts`, then fails on any change or untracked file under `frontend/packages/api-client`. [client-drift.log](client-drift.log) shows it passing on a clean checkout, then failing with exit 2 after a field is added to `HealthResponse` without regenerating. [ci-runs.log](ci-runs.log) shows the job passing in Actions. |
| 8 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Backend tests use the API seam (in-process `httpx.AsyncClient` with lifespan, real Postgres and Redis) and the task seam (eager, plus a real broker with an in-process worker). [backend-tests.log](backend-tests.log): 14 passed, 100% line+branch coverage. Frontend tests use the network seam (Testing Library + MSW with handlers typed from the generated schema). [frontend-tests.log](frontend-tests.log): 8 passed, and statements, branches, functions and lines are all 100%. [lint.log](lint.log): ruff, ruff format, mypy strict, eslint and tsc are all clean. [frontend-build.log](frontend-build.log): the production build succeeds. |
| 9 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | No domain terms were introduced. Health, worker and System status are technical or UI terms, not domain vocabulary, so `GLOSSARY.md` is unchanged. No ADR decision changed. Coverage exclusions stay within ADR-0008: `migrations/*` (covered by the round-trip test), the `__main__` block in `app/openapi.py`, and the generated `*.gen.ts`. The Studio entrypoint `main.tsx` is tested rather than excluded. No `pragma: no cover` is used. |

## Sandbox notes (local / test-double routes used)

- **Docker image builds.** The sandbox's egress proxy re-terminates TLS. Package downloads inside `docker build` therefore need its CA, and `ghcr.io` blob downloads are blocked by policy. Because of that block, `backend/Dockerfile` installs uv with `pip install uv==0.11.32` instead of copying it from `ghcr.io/astral-sh/uv`. To run the stack here, the images were built from the committed Dockerfiles with two lines added after `FROM`: copy the proxy CA in, and set the proxy environment. They were tagged `rag-agent-studio-{api,worker,beat,studio}` and started with `docker compose up -d --no-build --wait`. Everything else in `docker-compose.yml` was used unchanged. On a normal machine `make dev` builds the committed Dockerfiles directly.
- **No cloud credentials are needed for this ticket.** RustFS stands in for S3 and Mailpit for SES, as the spec intends. Neither is used by code yet; they are only started.
- **The Docker daemon** had to be started by hand in the sandbox (`dockerd`).

## Files

| File | What it is |
|---|---|
| `compose-stack.log` | `docker compose up`/`ps`, health curls, Mailpit/RustFS/pgvector checks, worker and Beat logs |
| `make-targets.log` | `make help` |
| `settings-fail-fast.log` | API and worker containers refusing to start with missing or invalid settings |
| `studio-status-page.png`, `studio-status-page-worker-stopped.png` | Studio System status page against the running stack (headless Chrome) |
| `alembic-round-trip.log` | Migration round-trip test, and the same round trip by hand in the API container |
| `backend-tests.log`, `frontend-tests.log` | Full suites with coverage reports (fresh clone) |
| `lint.log` | `make lint`: ruff check, ruff format --check, mypy --strict, eslint, tsc (fresh clone) |
| `frontend-build.log` | `pnpm build` (fresh clone) |
| `client-drift.log` | `make check-client` passing, then failing on simulated drift |
| `coverage-gate-demo.log` | Backend and frontend coverage gates failing when a test is removed |
| `ci-runs.log` | GitHub Actions results for this branch |
