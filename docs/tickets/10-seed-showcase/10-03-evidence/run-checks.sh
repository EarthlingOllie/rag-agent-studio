# Every check for 10-03, one at a time, from the branch's committed tree. Logs go to $L, then are
# copied into this folder. Backend services and the e2e stack are this ticket's own (rag1003-*).
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
C=${C:-$S/wt1003}; L=${L:-$S/ev1003-logs}; mkdir -p $L; E=docs/tickets/10-seed-showcase/10-03-evidence
export C L
cd $C; SHA=$(git rev-parse --short HEAD); echo $SHA > $L/sha
H="@ $SHA (ticket/10-03-demo-host-pages in $(basename $C), clean tree: $(git status --porcelain | wc -l) changes)"
export TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:48752/studio_test
export TEST_REDIS_URL=redis://localhost:48779/15
export TEST_OBJECT_STORE_URL=http://localhost:48791
(echo "\$ make install $H"; timeout 1800 make install 2>&1; echo "exit $?") > $L/install.log
(echo "\$ make lint $H"; timeout 1800 make lint 2>&1; echo "exit $?") > $L/lint.log
(echo "\$ make check-client $H"; timeout 900 make check-client 2>&1; echo "exit $?"; echo "\$ git status --porcelain"; git status --porcelain) > $L/client-drift.log
(echo "\$ make test-frontend $H"; timeout 3600 make test-frontend 2>&1; echo "exit $?") > $L/frontend-tests.log
docker rm -f rag1003-pg rag1003-redis rag1003-rustfs >/dev/null 2>&1
docker run -d --name rag1003-pg -p 48752:5432 -e POSTGRES_USER=studio -e POSTGRES_PASSWORD=studio -e POSTGRES_DB=studio pgvector/pgvector:0.8.1-pg16 >/dev/null
docker run -d --name rag1003-redis -p 48779:6379 redis:7.4.2-alpine >/dev/null
docker run -d --name rag1003-rustfs -p 48791:9000 -e RUSTFS_ACCESS_KEY=studio -e RUSTFS_SECRET_KEY=studio-secret rustfs/rustfs:1.0.4 >/dev/null
for i in $(seq 60); do docker exec rag1003-pg pg_isready -U studio >/dev/null 2>&1 && break; sleep 2; done; sleep 3
docker exec rag1003-pg psql -U studio -c "CREATE DATABASE studio_test" >/dev/null
(echo "\$ make test-backend (TEST_* -> fresh rag1003-pg/redis/rustfs) $H"; timeout 9000 make test-backend 2>&1 | grep -Eav '^\{"(name|timestamp)"'; echo "exit ${PIPESTATUS[0]}") > $L/backend-tests.log
docker rm -f rag1003-pg rag1003-redis rag1003-rustfs >/dev/null 2>&1
(echo "\$ TF_CLI_CONFIG_FILE=<scratch filesystem mirror of hashicorp/aws> make infra-check $H"; TF_CLI_CONFIG_FILE=$S/tf0906.rc timeout 2400 make infra-check 2>&1; echo "exit $?") > $L/infra-check.log
(echo "\$ gitleaks git (origin/candidate..HEAD) $H"; gitleaks git --log-opts="origin/candidate..HEAD" . 2>&1; echo "exit $?"; echo "\$ make audit $H"; timeout 900 make audit 2>&1; echo "exit $?") > $L/security.log
# RUN_E2E=0 skips images and e2e when run-e2e.sh already ran green on the same code.
[ "${RUN_E2E:-1}" = 1 ] && bash $C/$E/run-e2e.sh
for f in install lint client-drift frontend-tests backend-tests infra-check security images e2e; do echo "$f: $(grep -a '^exit' $L/$f.log | tr '\n' ' ')"; done
echo ALLDONE
