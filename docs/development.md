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

## Tests

Backend tests run against real Postgres and Redis. With `make services` running they use the `studio_test` database and Redis database 15; override with `TEST_DATABASE_URL` and `TEST_REDIS_URL`.
