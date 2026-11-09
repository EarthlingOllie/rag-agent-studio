# After the last re-merge of origin/candidate (07-08 Organisation cost, merged during the final gate):
# lint, client drift, link check, frontend suite, the backend modules the merge brought in, then the
# whole e2e suite again (the five-minute demo gained its Organisation cost step). One at a time.
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
C=${C:-$S/wt1006}; L=${L:-$S/ev1006-remerge}; mkdir -p $L; E=docs/tickets/10-seed-showcase/10-06-evidence
cd $C; SHA=$(git rev-parse --short HEAD)
H="@ $SHA (ticket/10-06-readme-demo in $(basename $C), clean tree: $(git status --porcelain | wc -l) changes)"
(echo "\$ make lint $H"; timeout 1800 make lint 2>&1; echo "exit $?") > $L/lint.log
(echo "\$ make check-client $H"; timeout 900 make check-client 2>&1; echo "exit $?"; echo "\$ git status --porcelain"; git status --porcelain) > $L/client-drift.log
(echo "\$ make link-check $H"; timeout 600 make link-check 2>&1; echo "exit $?") > $L/link-check.log
(echo "\$ make test-frontend $H"; timeout 3600 make test-frontend 2>&1; echo "exit $?") > $L/frontend-tests.log
docker rm -f rag1006-pg rag1006-redis rag1006-rustfs >/dev/null 2>&1
docker run -d --name rag1006-pg -p 49852:5432 -e POSTGRES_USER=studio -e POSTGRES_PASSWORD=studio -e POSTGRES_DB=studio pgvector/pgvector:0.8.1-pg16 >/dev/null
docker run -d --name rag1006-redis -p 49879:6379 redis:7.4.2-alpine >/dev/null
docker run -d --name rag1006-rustfs -p 49891:9000 -e RUSTFS_ACCESS_KEY=studio -e RUSTFS_SECRET_KEY=studio-secret rustfs/rustfs:1.0.4 >/dev/null
for i in $(seq 60); do docker exec rag1006-pg pg_isready -U studio >/dev/null 2>&1 && break; sleep 2; done; sleep 3
docker exec rag1006-pg psql -U studio -c "CREATE DATABASE studio_test" >/dev/null
export TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:49852/studio_test TEST_REDIS_URL=redis://localhost:49879/15 TEST_OBJECT_STORE_URL=http://localhost:49891
T="tests/integration/test_organisation_cost.py tests/integration/test_openapi.py tests/integration/test_tenant_isolation.py tests/integration/test_seed.py tests/integration/test_seeded_history.py"
(echo "\$ cd backend && uv run pytest --no-cov $T $H"; cd backend && timeout 1800 uv run pytest --no-cov $T 2>&1 | grep -Eav '^\{"(name|timestamp)"' | tail -15; echo "exit ${PIPESTATUS[0]}") > $L/backend-merged.log
docker rm -f rag1006-pg rag1006-redis rag1006-rustfs >/dev/null 2>&1
L=$L timeout 5000 bash $E/run-e2e.sh
for f in lint client-drift link-check frontend-tests backend-merged images e2e; do echo "$f: $(grep -a '^exit' $L/$f.log | tr '\n' ' ')"; done
