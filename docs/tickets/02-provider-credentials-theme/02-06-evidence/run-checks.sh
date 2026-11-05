#!/usr/bin/env bash
# Runs every check from a fresh clone, one log per check: the command, its output, its exit code.
# Postgres, Redis and RustFS: compose project rag0206 (compose.sandbox.yml ports), up before this runs.
set -u
CLONE=$1; OUT=$2
export TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:45632/studio_test
export TEST_REDIS_URL=redis://localhost:46206/15
export TEST_OBJECT_STORE_URL=http://localhost:49206
run() {
  local log=$1; shift
  {
    echo "\$ $*"; echo "# $(date -u +%FT%TZ) in a fresh clone at $(git -C "$CLONE" rev-parse --short HEAD)"
    (cd "$CLONE" && eval "$@") 2>&1 | grep -v '^{"name"\|^{"timestamp"\|^warning: The `UV_NATIVE_TLS`'
    echo "# exit code: ${PIPESTATUS[0]}"
  } > "$OUT/$log"
}
run install.log "make install"
run lint.log "make lint"
run backend-tests.log "make test-backend"
run frontend-tests.log "make test-frontend"
run client-drift.log "make check-client"
run studio-build.log "cd frontend && pnpm build"
run theme-image-api-tests.log "cd backend && uv run pytest -v --no-cov -p no:logging tests/integration/test_theme_images.py tests/integration/test_object_store.py tests/integration/test_theme.py tests/integration/test_migrations.py 'tests/integration/test_tenant_isolation.py' -k 'theme or Theme or images or declares or rustfs or migration or round'"
run security.log "make audit && gitleaks git --redact --no-banner --log-opts=HEAD ."
