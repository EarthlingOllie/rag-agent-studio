# After re-merging origin/candidate (0b77e0c, #78 07-07 Retention and tombstones) on top of the final gate at 5ab7512:
# the merge was clean and touched none of this ticket's files, so per the test policy only the cheap whole-repo checks
# and the backend modules touched by this ticket or by the merged change that meet it (seed, worker/Beat, retention)
# are re-run. Logs go to $L.
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
C=${C:-$S/wt1005}; L=${L:-$S/ev1005-remerge}; mkdir -p $L
cd $C; SHA=$(git rev-parse --short HEAD)
H="@ $SHA ($(git rev-parse --abbrev-ref HEAD) in $(basename $C), clean tree: $(git status --porcelain | wc -l) changes)"
(echo "\$ make install && make lint $H"; timeout 1800 make install >/dev/null 2>&1 && timeout 1800 make lint 2>&1; echo "exit $?") > $L/remerge-lint.log
(echo "\$ make check-client $H"; timeout 900 make check-client 2>&1; echo "exit $?"; echo "\$ git status --porcelain"; git status --porcelain) > $L/remerge-client-drift.log
(echo "\$ TF_CLI_CONFIG_FILE=<scratch mirror> make infra-check $H"; TF_CLI_CONFIG_FILE=$S/tf0906.rc timeout 2400 make infra-check 2>&1; echo "exit $?") > $L/remerge-infra-check.log
export TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:48952/studio_test
export TEST_REDIS_URL=redis://localhost:48979/15
export TEST_OBJECT_STORE_URL=http://localhost:48991
docker rm -f rag1005-pg rag1005-redis rag1005-rustfs >/dev/null 2>&1
docker run -d --name rag1005-pg -p 48952:5432 -e POSTGRES_USER=studio -e POSTGRES_PASSWORD=studio -e POSTGRES_DB=studio pgvector/pgvector:0.8.1-pg16 >/dev/null
docker run -d --name rag1005-redis -p 48979:6379 redis:7.4.2-alpine >/dev/null
docker run -d --name rag1005-rustfs -p 48991:9000 -e RUSTFS_ACCESS_KEY=studio -e RUSTFS_SECRET_KEY=studio-secret rustfs/rustfs:1.0.4 >/dev/null
for i in $(seq 60); do docker exec rag1005-pg pg_isready -U studio >/dev/null 2>&1 && break; sleep 2; done; sleep 3
docker exec rag1005-pg psql -U studio -c "CREATE DATABASE studio_test" >/dev/null
T="tests/unit/test_aws_task_settings.py tests/integration/test_seed.py tests/integration/test_seeded_history.py tests/integration/test_worker_entrypoint.py tests/integration/test_retention.py tests/integration/test_migrations.py"
T=$(cd backend && for t in $T; do [ -e $t ] && printf '%s ' $t; done)
(echo "\$ cd backend && pytest --no-cov $T $H"; cd backend && timeout 3600 uv run pytest --no-cov $T 2>&1 | grep -Eav '^\{"(name|timestamp)"' | tail -15; echo "exit ${PIPESTATUS[0]}") > $L/remerge-backend.log
docker rm -f rag1005-pg rag1005-redis rag1005-rustfs >/dev/null 2>&1
for f in remerge-lint remerge-client-drift remerge-infra-check remerge-backend; do echo "$f: $(grep -a '^exit' $L/$f.log | tr '\n' ' ')"; done
echo ALLDONE
