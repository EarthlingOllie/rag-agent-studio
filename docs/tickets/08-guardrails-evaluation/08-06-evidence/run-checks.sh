set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
C=$S/ev0806-clone; L=$S/ev0806-logs; mkdir -p $L; rm -rf $C; rm -f $L/*
git clone -q --depth 50 --branch ticket/08-06-guardrail-analytics-alerts https://github.com/EarthlingOllie/rag-agent-studio $C || { echo CLONEFAIL > $L/summary; exit 1; }
cd $C; git rev-parse --short HEAD > $L/head
docker rm -f rag0806-evpg rag0806-evredis rag0806-evrustfs >/dev/null 2>&1
docker run -d --name rag0806-evpg -e POSTGRES_USER=studio -e POSTGRES_PASSWORD=studio -e POSTGRES_DB=studio -p 48252:5432 pgvector/pgvector:0.8.1-pg16 >/dev/null
docker run -d --name rag0806-evredis -p 48253:6379 redis:7.4.2-alpine >/dev/null
docker run -d --name rag0806-evrustfs -e RUSTFS_ACCESS_KEY=studio -e RUSTFS_SECRET_KEY=studio-secret -e RUSTFS_VOLUMES=/data -p 48254:9000 rustfs/rustfs:1.0.4 rustfs >/dev/null
export TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:48252/studio_test TEST_REDIS_URL=redis://localhost:48253/15 TEST_OBJECT_STORE_URL=http://localhost:48254
for f in install lint client backend frontend; do echo "$(git rev-parse --short HEAD)" > $L/$f.log; done
(timeout 1800 make install 2>&1 | tail -15; echo "exit ${PIPESTATUS[0]}") >> $L/install.log
(timeout 1800 make lint 2>&1 | tail -30; echo "exit ${PIPESTATUS[0]}") >> $L/lint.log
(timeout 900 make check-client 2>&1 | tail -10; echo "exit ${PIPESTATUS[0]}") >> $L/client.log
for i in $(seq 30); do docker exec rag0806-evpg pg_isready -U studio >/dev/null 2>&1 && break; sleep 2; done
docker exec rag0806-evpg psql -U studio -c "CREATE DATABASE studio_test" >/dev/null
(timeout 2400 make test-frontend 2>&1 | tail -40; echo "exit ${PIPESTATUS[0]}") >> $L/frontend.log
(timeout 7000 make test-backend 2>&1 | grep -vE '^\{"' | tail -80; echo "exit ${PIPESTATUS[0]}") >> $L/backend.log
docker rm -f rag0806-evpg rag0806-evredis rag0806-evrustfs >/dev/null 2>&1
for f in install lint client frontend backend; do echo "$f: $(grep -a '^exit' $L/$f.log)"; done > $L/summary
echo ALLDONE >> $L/summary
