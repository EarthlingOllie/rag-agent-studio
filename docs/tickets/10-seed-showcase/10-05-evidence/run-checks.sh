# Every check for 10-05, one at a time, from the branch's committed tree. Logs go to $L, then are copied into this
# folder. Backend services and the e2e stack are this ticket's own (rag1005-*). Each full suite runs once.
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
C=${C:-$S/wt1005}; L=${L:-$S/ev1005-logs}; mkdir -p $L; E=docs/tickets/10-seed-showcase/10-05-evidence
export C L
cd $C; SHA=$(git rev-parse --short HEAD); echo $SHA > $L/sha
H="@ $SHA ($(git rev-parse --abbrev-ref HEAD) in $(basename $C), clean tree: $(git status --porcelain | wc -l) changes)"
export TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:48952/studio_test
export TEST_REDIS_URL=redis://localhost:48979/15
export TEST_OBJECT_STORE_URL=http://localhost:48991
(echo "\$ make install $H"; timeout 1800 make install 2>&1; echo "exit $?") > $L/install.log
(echo "\$ make lint $H"; timeout 1800 make lint 2>&1; echo "exit $?") > $L/lint.log
(echo "\$ actionlint + shellcheck (scratch venv: actionlint-py, shellcheck-py) $H"; PATH=$S/tools0906/.venv/bin:$PATH
 actionlint -version | head -1; actionlint .github/workflows/*.yml && echo "actionlint: every workflow clean"; echo "exit $?"
 shellcheck --version | sed -n 2p; shellcheck scripts/deploy/*.sh scripts/deploy/tests/*.sh scripts/deploy/tests/stubs/* && echo "shellcheck: clean"; echo "exit $?") > $L/workflow-lint.log
(echo "\$ make check-client $H"; timeout 900 make check-client 2>&1; echo "exit $?"; echo "\$ git status --porcelain"; git status --porcelain) > $L/client-drift.log
(echo "\$ TF_CLI_CONFIG_FILE=<scratch filesystem mirror of hashicorp/aws> make infra-check $H"; TF_CLI_CONFIG_FILE=$S/tf0906.rc timeout 2400 make infra-check 2>&1; echo "exit $?") > $L/infra-check.log
(echo "\$ make test-frontend $H"; timeout 3600 make test-frontend 2>&1; echo "exit $?") > $L/frontend-tests.log
docker rm -f rag1005-pg rag1005-redis rag1005-rustfs >/dev/null 2>&1
docker run -d --name rag1005-pg -p 48952:5432 -e POSTGRES_USER=studio -e POSTGRES_PASSWORD=studio -e POSTGRES_DB=studio pgvector/pgvector:0.8.1-pg16 >/dev/null
docker run -d --name rag1005-redis -p 48979:6379 redis:7.4.2-alpine >/dev/null
docker run -d --name rag1005-rustfs -p 48991:9000 -e RUSTFS_ACCESS_KEY=studio -e RUSTFS_SECRET_KEY=studio-secret rustfs/rustfs:1.0.4 >/dev/null
for i in $(seq 60); do docker exec rag1005-pg pg_isready -U studio >/dev/null 2>&1 && break; sleep 2; done; sleep 3
docker exec rag1005-pg psql -U studio -c "CREATE DATABASE studio_test" >/dev/null
(echo "\$ TEST_WORKERS=3 make test-backend (TEST_* -> fresh rag1005-pg/redis/rustfs) $H"; TEST_WORKERS=3 timeout 9000 make test-backend 2>&1 | grep -Eav '^\{"(name|timestamp)"'; echo "exit ${PIPESTATUS[0]}") > $L/backend-tests.log
docker rm -f rag1005-pg rag1005-redis rag1005-rustfs >/dev/null 2>&1
(echo "\$ gitleaks git (origin/candidate..HEAD) $H"; gitleaks git --log-opts="origin/candidate..HEAD" . 2>&1; echo "exit $?") > $L/security.log
[ "${RUN_E2E:-1}" = 1 ] && bash $C/$E/run-e2e.sh
for f in install lint workflow-lint client-drift infra-check frontend-tests backend-tests security images ecs-seed e2e; do echo "$f: $(grep -a '^exit' $L/$f.log 2>/dev/null | tr '\n' ' ')"; done
echo ALLDONE
