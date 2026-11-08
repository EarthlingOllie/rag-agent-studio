# Evidence: chore-test-sharding, Parallel backend test suite (pytest-xdist)

Infra chore approved by the user on 2026-11-08; there is no ticket file, so there is no claim or Status line to change. Branch `ticket/chore-test-sharding-test-sharding-xdist` (the branch name the dispatch gave; the brief also mentions `chore/test-sharding`, see judgement calls), from `origin/candidate` at `e0ffa02` (07-06 merged). The change is commit `3f1cec3`. `origin/candidate` was still `e0ffa02` when both suite runs finished, so `3f1cec3` is the final code commit after the last merge check; only this folder was written afterwards. Each log's first line names the commit.

**Result:** the backend suite gives the same results serially and on 3 xdist workers: 2422 passed, 0 failed, 0 skipped, 100.00% line and branch coverage in both runs. It took 55 min 44 s serially and 28 min 16 s on 3 workers (1.97 times faster) on a shared 4-CPU machine with other jobs' suites running.

## What was built

- **`backend/tests/worker_resources.py`** (new): `worker_database_url`, `worker_redis_url` and `ensure_database`.
  - Under xdist (`PYTEST_XDIST_WORKER` = `gw0`, `gw1`, ...), the database becomes `<name>_<worker id>` (`studio_test_gw0`, ...). The rest of the URL, query string included, is kept.
  - Each worker's Redis database counts down from the serial one: with `/15`, `gw0` uses 14, `gw1` uses 13, and so on down to `gw14` on 0. More workers than that is refused with a clear error rather than sharing a database.
  - `ensure_database` creates a missing database through the server's `postgres` admin database. It is idempotent.
  - A serial run (no worker id, `""` or `master`) keeps the configured URLs exactly.
- **`backend/tests/conftest.py`**: `TEST_DATABASE_URL` and `TEST_REDIS_URL` are now this worker's URLs, derived from the environment's (`BASE_DATABASE_URL` and `BASE_REDIS_URL`). Every test and fixture that already imported them (the app's environment, the Alembic migration, the direct engines in five test modules, the broker flushes in `test_telemetry.py` and `test_worker_health.py`) follows the worker without change. `database_schema` stays session-scoped, so it migrates once per worker.
- **`backend/tests/integration/conftest.py`** (new): a session-scoped autouse `worker_database` fixture creates this worker's database before any integration test runs. Tests that build their own app or run Alembic without `database_schema` (for example `test_migrations.py` and `test_health.py`) can then run first on a worker. Unit tests still need no Postgres.
- **`backend/tests/integration/test_object_store.py`**: the shared RustFS test bucket is `studio-documents-test-<worker id>` under xdist (unchanged when serial). Otherwise two workers could both see it missing and race to create it on a fresh RustFS.
- **`backend/pyproject.toml` / `uv.lock`**: `pytest-xdist>=3.8.0` added to the `dev` group (locks `pytest-xdist 3.8.0` and `execnet 2.1.2`). The pytest `addopts` are unchanged (`--cov=app --cov-branch`, `fail_under = 100`). pytest-cov combines the workers' coverage.
- **`Makefile`**: `test-backend` runs `uv run pytest -n $(TEST_WORKERS)` when `TEST_WORKERS` is set (a number or `auto`). Unset runs serially, as before.
- **`.github/workflows/backend.yml`**: the test step runs `uv run pytest -n auto`. The Postgres service still creates only `studio_test`, and the workers create their own databases.

## Test seams

These seams were not confirmed with a human (none is available in this run). They are the public interfaces of the change:

- **The naming functions:** `backend/tests/unit/test_worker_resources.py` (6 tests, 8 cases). Serial names are kept (`None`, `""`, `master`). Each worker gets its own database, and the query string is kept. Redis databases count down from the serial one to 0. Running out of Redis databases is refused, and so is a Redis URL with no database (counting down from 0).
- **The running suite:** `backend/tests/integration/test_worker_resources.py` (3 tests). A missing database is created once, and a second call does nothing. The suite's URLs are this worker's. The app really connects to this worker's databases: Postgres `current_database()` and the Redis connection's `db`.
- **The whole suite as the behaviour under test:** the serial and `-n 3` runs below.

These test helpers live in `tests/`, outside the `--cov=app` gate. They are covered by the tests above, not by the coverage figure.

## Acceptance criteria

| # | Criterion (from the approved brief) | Evidence |
|---|---|---|
| 1 | pytest-xdist in the backend dev dependency group, `uv.lock` updated | `backend/pyproject.toml` `dev` group: `pytest-xdist>=3.8.0`. `backend/uv.lock`: `pytest-xdist 3.8.0` and `execnet 2.1.2`. The `-n 3` run's header in [backend-tests-xdist-n3.log](backend-tests-xdist-n3.log) and the log body show `cd backend && uv run pytest -n 3` running with xdist installed. |
| 2 | A per-worker database `studio_test_<worker_id>`, created if missing through an admin connection and migrated once per worker | `ensure_database` (admin `postgres` database, `CREATE DATABASE` only if `pg_database` lacks it), called by the autouse `worker_database` fixture. `database_schema` is session-scoped, so it migrates once per worker process. Tests: `test_a_missing_database_is_created_once`, `test_each_worker_gets_its_own_database`, `test_the_database_query_string_is_kept`, `test_the_app_talks_to_this_workers_databases`. After the `-n 3` run, [worker-databases.log](worker-databases.log) shows `studio_test_gw0`, `studio_test_gw1` and `studio_test_gw2` each at Alembic head `0037_usage_daily`, holding 1129, 613 and 986 Organisations. The serial `studio_test` was untouched by that run (2 Organisations, written by the serial run that had just started). |
| 3 | A per-worker Redis database index, so workers never share state | `worker_redis_url`: one database per worker below the serial one. Tests: `test_each_worker_gets_a_redis_database_below_the_serial_one`, `test_more_workers_than_redis_databases_is_refused`, `test_a_redis_url_without_a_database_counts_down_from_database_0`, `test_the_app_talks_to_this_workers_databases`. The `flushdb()` broker resets in `test_telemetry.py` and `test_worker_health.py`, and the app fixture's key sweep, now touch only the worker's own database. Celery's broker and result backend follow `REDIS_URL`, so a worker's `start_worker` never takes another worker's tasks. |
| 4 | A serial run (no `-n`) keeps today's names exactly | `test_a_serial_run_keeps_the_configured_names[None/""/master]`. `test_the_suite_uses_this_workers_databases` passes in both runs. The serial run, [backend-tests-serial.log](backend-tests-serial.log), used `studio_test` and Redis `/15` ([worker-databases.log](worker-databases.log): `db15` holds the serial run's keys). |
| 5 | `make test-backend` honours `TEST_WORKERS` (unset = serial) | [make-dry-run.log](make-dry-run.log): unset gives `uv run pytest`, `TEST_WORKERS=3` gives `uv run pytest -n 3`, and `TEST_WORKERS=auto` gives `uv run pytest -n auto`. Both suite runs went through `make test-backend`. |
| 6 | The CI workflow may pass `-n auto` | `.github/workflows/backend.yml`: `run: uv run pytest -n auto`. GitHub Actions is down (per the user), so this was not run on GitHub; see gaps. |
| 7 | Tests that assume global state are fixed, not skipped or quarantined | I audited `backend/tests` for global state: the shared database name (the migration round trip downgrades the whole database to base), Redis `flushdb`, rate-limit and lockout keys, the Celery broker, the shared RustFS bucket, fixed ports, temp paths and module caches. Fixes:<br>• The database and Redis are per worker (criteria 2 and 3).<br>• The RustFS bucket is per worker.<br>• Every integration test can reach its worker's database whatever runs first.<br>No ports or temp paths are fixed: `test_mailer.py` picks a free port, and other buckets and keys are uuid-named. Module caches are per process. No test was skipped, marked or deselected (the 24 deselected are the `live` tests, deselected by `addopts` exactly as before). |
| 8 | Same results serial and `-n 3` on the same final commit, coverage 100% in both, wall-clock of each | Both runs are on `3f1cec3`, against fresh `ragshard-*` Postgres/pgvector, Redis and RustFS containers (Redis flushed before each run):<br>• **Serial** ([backend-tests-serial.log](backend-tests-serial.log)): 2422 passed, 0 failed, 0 skipped, 0 errors (24 `live` deselected). TOTAL 11214 statements and 1346 branches, 0 missed, 100.00%, "Required test coverage of 100.0% reached". pytest 3319 s; wall-clock **3344 s (55 min 44 s)**. Exit 0.<br>• **`-n 3`** ([backend-tests-xdist-n3.log](backend-tests-xdist-n3.log)): 2422 passed, 0 failed, 0 skipped, 0 errors. The same TOTAL 11214 / 1346, 0 missed, 100.00%. pytest 1679 s; wall-clock **1696 s (28 min 16 s)**. Exit 0.<br>xdist's summary line leaves out the `deselected` count, because deselection happens on the workers. Both runs pass the same 2422 tests. |
| — | Lint and type check | [backend-lint.log](backend-lint.log): `make lint-backend` (`ruff check`, `ruff format --check`, `mypy --strict` over 374 files, new modules included) all pass at `3f1cec3`. |

Frontend and e2e suites: not affected (no frontend, e2e or compose files changed) and not rerun, as the brief allows.

## Gaps and judgement calls

- **CI not run on GitHub:** GitHub Actions is down. The `-n auto` workflow step is verified only by the local `-n 3` run and the Make dry run. `-n auto` on a runner with 2 to 4 CPUs uses Redis databases 14 down to 11, well within the 15 available.
- **Branch name:** the dispatch's TASK line names `ticket/chore-test-sharding-test-sharding-xdist`, and the context note says `chore/test-sharding`. I used the TASK line's name, as it was given twice as "your branch". The PR title should be "Chore: parallel backend test suite (pytest-xdist)". The orchestrator opens the PR, not this run.
- **Redis isolation uses database indexes, not key prefixes:** the broker flushes (`flushdb`) and Celery's queues cannot be key-prefixed without app changes. The limit is 15 parallel workers with the default `/15`.
- **The app's `S3ObjectStore.prepare` still races** if two processes create the same missing bucket at once. That is app behaviour outside this chore's scope. The test suite no longer triggers it (per-worker bucket).
- **Wall-clock figures** were taken on a shared, loaded 4-CPU machine (load average around 8 during the `-n 3` run). The speed-up on a dedicated runner should be at least as good.
- **No human confirmed the test seams.** They are recorded above.
