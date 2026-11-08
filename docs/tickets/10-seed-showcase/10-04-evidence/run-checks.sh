# Every non-e2e check for 10-04, one at a time, from the branch's committed tree (git status
# empty). Logs go to $L, then are copied into this folder. Backend services are this ticket's own
# fresh rag1004-pg/redis/rustfs containers. The e2e run is run-e2e.sh.
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
C=${C:-$S/wt1004}; L=${L:-$S/ev1004-logs}; mkdir -p $L
cd $C; SHA=$(git rev-parse --short HEAD)
H="@ $SHA (ticket/10-04-attack-panel in $(basename $C), clean tree: $(git status --porcelain | wc -l) changes)"
export TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:48852/studio_test
export TEST_REDIS_URL=redis://localhost:48879/15
export TEST_OBJECT_STORE_URL=http://localhost:48891
(echo "\$ make install $H"; timeout 1800 make install 2>&1; echo "exit $?") > $L/install.log
(echo "\$ make lint $H"; timeout 1800 make lint 2>&1; echo "exit $?") > $L/lint.log
(echo "\$ make check-client $H"; timeout 900 make check-client 2>&1; echo "exit $?"; echo "\$ git status --porcelain"; git status --porcelain) > $L/client-drift.log
(echo "\$ make test-frontend $H"; timeout 3600 make test-frontend 2>&1; echo "exit $?") > $L/frontend-tests.log
(echo "\$ scripts/deploy/tests/deploy.test.sh $H"; timeout 600 scripts/deploy/tests/deploy.test.sh 2>&1; echo "exit $?") > $L/deploy-tests.log
docker rm -f rag1004-pg rag1004-redis rag1004-rustfs >/dev/null 2>&1
docker run -d --name rag1004-pg -p 48852:5432 -e POSTGRES_USER=studio -e POSTGRES_PASSWORD=studio -e POSTGRES_DB=studio pgvector/pgvector:0.8.1-pg16 >/dev/null
docker run -d --name rag1004-redis -p 48879:6379 redis:7.4.2-alpine >/dev/null
docker run -d --name rag1004-rustfs -p 48891:9000 -e RUSTFS_ACCESS_KEY=studio -e RUSTFS_SECRET_KEY=studio-secret rustfs/rustfs:1.0.4 >/dev/null
for i in $(seq 60); do docker exec rag1004-pg pg_isready -U studio >/dev/null 2>&1 && break; sleep 2; done; sleep 3
docker exec rag1004-pg psql -U studio -c "CREATE DATABASE studio_test" >/dev/null
(echo "\$ TEST_WORKERS=3 make test-backend (TEST_* -> fresh rag1004-pg/redis/rustfs) $H"; TEST_WORKERS=3 timeout 7200 make test-backend 2>&1 | grep -Eav '^\{"(name|timestamp)"'; echo "exit ${PIPESTATUS[0]}") > $L/backend-tests.log
(echo "\$ gitleaks git (origin/candidate..HEAD) $H"; gitleaks git --log-opts="origin/candidate..HEAD" . 2>&1; echo "exit $?"; echo "\$ make audit $H"; timeout 900 make audit 2>&1; echo "exit $?") > $L/security.log
for f in install lint client-drift frontend-tests deploy-tests backend-tests security; do echo "$f: $(grep -a '^exit' $L/$f.log | tr '\n' ' ')"; done
echo ALLDONE
