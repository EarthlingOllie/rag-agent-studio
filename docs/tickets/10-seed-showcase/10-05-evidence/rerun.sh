# Re-runs, per the test policy, only what failed in the full-suite runs, plus the touched modules, on the images
# run-e2e.sh built (rag-agent-studio/*:1005) and on fresh rag1005-* backend services.
# 1. e2e: the two analytics specs whose Version locator was fixed, and the spec that was flaky.
# RERUN_BACKEND=0 skips step 2 when it already passed on the same backend code.
# 2. backend: tests/integration/test_logging.py (4 subprocess-startup timeouts under load in the full run), the
#    touched settings test and the seed tests.
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
C=${C:-$S/wt1005}; L=${L:-$S/ev1005-logs}; mkdir -p $L; E=docs/tickets/10-seed-showcase/10-05-evidence
cd $C; SHA=$(git rev-parse --short HEAD)
H="@ $SHA ($(git rev-parse --abbrev-ref HEAD) in $(basename $C), clean tree: $(git status --porcelain | wc -l) changes)"
set -a; . $E/e2e.env; set +a
COMPOSE="docker compose -p rag1005-e2e -f docker-compose.yml -f $E/compose.sandbox.yml"
SPECS="tests/guardrail-analytics.spec.ts tests/version-kpis.spec.ts tests/members.spec.ts"
(echo "\$ CI=1: $COMPOSE up -d --wait; make seed COMPOSE=...; cd frontend && pnpm e2e $SPECS $H"
 $COMPOSE up -d --wait 2>&1 && make seed COMPOSE="$COMPOSE" 2>&1 && (cd frontend && CI=1 timeout 1800 pnpm e2e $SPECS 2>&1); echo "exit $?") > $L/e2e-rerun.log
$COMPOSE down -v >/dev/null 2>&1
grep -aq '^exit 0' $L/e2e-rerun.log && docker rmi rag-agent-studio/api:1005 rag-agent-studio/studio:1005 >/dev/null 2>&1
if [ "${RERUN_BACKEND:-1}" = 1 ]; then
export TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:48952/studio_test
export TEST_REDIS_URL=redis://localhost:48979/15
export TEST_OBJECT_STORE_URL=http://localhost:48991
docker rm -f rag1005-pg rag1005-redis rag1005-rustfs >/dev/null 2>&1
docker run -d --name rag1005-pg -p 48952:5432 -e POSTGRES_USER=studio -e POSTGRES_PASSWORD=studio -e POSTGRES_DB=studio pgvector/pgvector:0.8.1-pg16 >/dev/null
docker run -d --name rag1005-redis -p 48979:6379 redis:7.4.2-alpine >/dev/null
docker run -d --name rag1005-rustfs -p 48991:9000 -e RUSTFS_ACCESS_KEY=studio -e RUSTFS_SECRET_KEY=studio-secret rustfs/rustfs:1.0.4 >/dev/null
for i in $(seq 60); do docker exec rag1005-pg pg_isready -U studio >/dev/null 2>&1 && break; sleep 2; done; sleep 3
docker exec rag1005-pg psql -U studio -c "CREATE DATABASE studio_test" >/dev/null
T="tests/integration/test_logging.py tests/unit/test_aws_task_settings.py tests/integration/test_seed.py tests/integration/test_seeded_history.py"
(echo "\$ cd backend && pytest --no-cov $T $H"; cd backend && timeout 3600 uv run pytest --no-cov $T 2>&1 | grep -Eav '^\{"(name|timestamp)"' | tail -15; echo "exit ${PIPESTATUS[0]}") > $L/backend-rerun.log
docker rm -f rag1005-pg rag1005-redis rag1005-rustfs >/dev/null 2>&1
fi
echo "e2e-rerun: $(grep -a '^exit' $L/e2e-rerun.log) backend-rerun: $(grep -a '^exit' $L/backend-rerun.log)"
