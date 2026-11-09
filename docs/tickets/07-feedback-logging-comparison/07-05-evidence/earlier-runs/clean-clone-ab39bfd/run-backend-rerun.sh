set -u
S=${scratch}
L=$S/evalN0705-logs; mkdir -p $L; D=$S/evalN0705
rm -rf $D; git clone -q --branch ticket/07-05-version-comparison $(git -C /home/user/rag-agent-studio remote get-url origin) $D || { echo clonefail; exit 1; }
cd $D; git rev-parse HEAD > $L/head.txt
export TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:47055/studio_test TEST_REDIS_URL=redis://localhost:47056/15 TEST_OBJECT_STORE_URL=http://localhost:47057
F='^\{"(name|timestamp)"'
(cd backend && timeout 1800 uv sync --frozen 2>&1; echo "exit $?") > $L/install.log
for i in $(seq 720); do l=$(cut -d' ' -f1 /proc/loadavg); [ $(pgrep -fc "bin/pytest") -le 0 ] && awk -v l=$l 'BEGIN{exit !(l<6)}' && break; sleep 30; done; echo "gate waited $i load $(cat /proc/loadavg)" > $L/gate.txt
docker rm -f rag0705-evpg rag0705-evredis rag0705-evrustfs >/dev/null 2>&1
docker run -d --name rag0705-evpg -p 47055:5432 -e POSTGRES_USER=studio -e POSTGRES_PASSWORD=studio -e POSTGRES_DB=studio pgvector/pgvector:0.8.1-pg16 >/dev/null
docker run -d --name rag0705-evredis -p 47056:6379 redis:7.4.2-alpine >/dev/null
docker run -d --name rag0705-evrustfs -p 47057:9000 -e RUSTFS_ACCESS_KEY=studio -e RUSTFS_SECRET_KEY=studio-secret rustfs/rustfs:1.0.4 >/dev/null
for i in $(seq 60); do docker exec rag0705-evpg pg_isready -U studio >/dev/null 2>&1 && break; sleep 2; done; sleep 3
docker exec rag0705-evpg psql -U studio -c "CREATE DATABASE studio_test" >/dev/null
(echo "load at start: $(cat /proc/loadavg)"; timeout 6000 make test-backend TEST_WORKERS=3 2>&1 | grep --line-buffered -Eav "$F"; echo "exit ${PIPESTATUS[0]}") > $L/be.log
docker rm -f rag0705-evpg rag0705-evredis rag0705-evrustfs >/dev/null 2>&1
echo "be: $(grep -a '^exit' $L/be.log)"; echo ALLDONE
