set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
C=$S/wt0605; L=$S/ev0605-logs; mkdir -p $L; E=docs/tickets/06-embed-widget-operational-settings/06-05-evidence
cd $C; SHA=$(git rev-parse --short HEAD)
H="@ $SHA (ticket/06-05-rate-limits, clean tree: $(git status --porcelain | wc -l) changes)"
export TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:48552/studio_test
export TEST_REDIS_URL=redis://localhost:48579/15
export TEST_OBJECT_STORE_URL=http://localhost:48591
docker rm -f rag0605-pg rag0605-redis rag0605-rustfs >/dev/null 2>&1
docker run -d --name rag0605-pg -p 48552:5432 -e POSTGRES_USER=studio -e POSTGRES_PASSWORD=studio -e POSTGRES_DB=studio pgvector/pgvector:0.8.1-pg16 >/dev/null
docker run -d --name rag0605-redis -p 48579:6379 redis:7.4.2-alpine >/dev/null
docker run -d --name rag0605-rustfs -p 48591:9000 -e RUSTFS_ACCESS_KEY=studio -e RUSTFS_SECRET_KEY=studio-secret rustfs/rustfs:1.0.4 >/dev/null
for i in $(seq 60); do docker exec rag0605-pg pg_isready -U studio >/dev/null 2>&1 && break; sleep 2; done; sleep 3
docker exec rag0605-pg psql -U studio -c "CREATE DATABASE studio_test" >/dev/null
(echo "\$ make test-backend (TEST_* -> fresh rag0605-pg/redis/rustfs) $H"; timeout 7200 make test-backend 2>&1 | grep -Eav '^\{"(name|timestamp)"'; echo "exit ${PIPESTATUS[0]}") > $L/backend-tests.log
docker rm -f rag0605-pg rag0605-redis rag0605-rustfs >/dev/null 2>&1
(echo "\$ TF_CLI_CONFIG_FILE=<scratch filesystem mirror of hashicorp/aws 6.72.0> make infra-check $H"; TF_CLI_CONFIG_FILE=$S/tf0906.rc timeout 2400 make infra-check 2>&1; echo "exit $?") > $L/infra-check.log
(echo "\$ gitleaks git (origin/candidate..HEAD) $H"; gitleaks git --log-opts="origin/candidate..HEAD" . 2>&1; echo "exit $?"; echo "\$ make audit $H"; timeout 900 make audit 2>&1; echo "exit $?") > $L/security.log
df -h / | tail -1 > $L/df-before-images
(echo "\$ $E/build.sh (sandbox make images) $H"; bash $E/build.sh $C 0605 2>&1; echo "exit $?") > $L/images.log
set -a; . $E/e2e.env; set +a
COMPOSE="docker compose -p rag0605-e2e -f docker-compose.yml -f $E/compose.sandbox.yml"
SPECS="tests/rate-limits.spec.ts tests/embed.spec.ts tests/operational-settings.spec.ts tests/widget-lifecycle.spec.ts tests/widget-accessibility.spec.ts tests/branded-widget.spec.ts tests/playground.spec.ts tests/auth.spec.ts tests/smoke.spec.ts"
# make e2e's three steps, with the Playwright run limited to the specs this ticket touches.
(echo "\$ (env from e2e.env) CI=1: $COMPOSE up -d --build --wait; make seed COMPOSE=...; cd frontend && pnpm e2e $SPECS $H (CI settings: one retry)"
 $COMPOSE up -d --build --wait 2>&1 && make seed COMPOSE="$COMPOSE" 2>&1 && (cd frontend && CI=1 timeout 3600 pnpm e2e $SPECS 2>&1); echo "exit $?") > $L/e2e.log
$COMPOSE down -v >/dev/null 2>&1
docker rmi rag-agent-studio/api:0605 rag-agent-studio/studio:0605 >/dev/null 2>&1; docker builder prune -af >/dev/null 2>&1
for f in install lint client-drift frontend-tests backend-tests infra-check security images e2e; do echo "$f: $(grep -a '^exit' $L/$f.log | tr '\n' ' ')"; done
echo ALLDONE
