# Local development

Prerequisites: Docker with Compose v2, GNU Make, [uv](https://docs.astral.sh/uv/) and Node 22 with pnpm (via `corepack enable`).

| Command | What it does |
|---|---|
| `make dev` | Builds and starts the whole stack: Postgres with pgvector, Redis, RustFS, Mailpit, the API, the Celery worker, Celery Beat and the Studio. |
| `make install` | Installs backend (`uv sync`) and frontend (`pnpm install`) dependencies on the host. |
| `make services` | Starts only Postgres and Redis, which the backend tests need. |
| `make test` | Backend and frontend tests, each failing below 100% line or branch coverage (ADR-0008). |
| `make lint` | ruff, `mypy --strict`, eslint and `tsc`. |
| `make gen-client` | Regenerates `frontend/packages/api-client` from the backend's OpenAPI schema. |
| `make check-client` | Fails if the committed API client differs from a fresh generation (CI runs this). |

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
