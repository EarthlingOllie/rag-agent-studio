#!/usr/bin/env bash
# Runs every check from the fresh clone, one log per check: the command, its output, its exit code.
# Postgres and Redis: compose project rag0205 (postgres :55432, redis :56379; compose.sandbox.yml), up before this runs.
set -u
CLONE=$1; OUT=$2
export TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:55432/studio_test
export TEST_REDIS_URL=redis://localhost:56379/15
run() { local log=$1; shift; { echo "\$ $*"; echo "# $(date -u +%FT%TZ) in $CLONE at $(git -C "$CLONE" rev-parse --short HEAD)"; (cd "$CLONE" && eval "$@") 2>&1; echo "# exit code: $?"; } > "$OUT/$log"; }
run install.log "make install"
run lint.log "make lint"
run backend-tests.log "make test-backend"
run frontend-tests.log "make test-frontend"
run client-drift.log "make check-client"
run studio-build.log "cd frontend && pnpm build"
run theme-api-tests.log "cd backend && uv run pytest -v --no-cov tests/integration/test_theme.py tests/integration/test_tenant_isolation.py -k 'theme or Theme or every or declares'"
run security.log "make audit && gitleaks git --redact --no-banner --log-opts=HEAD ."
