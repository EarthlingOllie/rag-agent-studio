set -u
S=${scratch}
L=$S/evalM0705-logs; mkdir -p $L; D=$S/evalM0705
rm -rf $D; git clone -q --branch ticket/07-05-version-comparison $(git -C /home/user/rag-agent-studio remote get-url origin) $D || { echo clonefail; exit 1; }
cd $D; H=$(git rev-parse --short HEAD); echo $H > $L/head.txt; E=docs/tickets/07-feedback-logging-comparison/07-05-evidence
export TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:47055/studio_test TEST_REDIS_URL=redis://localhost:47056/15 TEST_OBJECT_STORE_URL=http://localhost:47057
F='^\{"(name|timestamp)"'
(timeout 1800 make install 2>&1; echo "exit $?") > $L/install.log
(timeout 1800 make lint 2>&1; echo "exit $?") > $L/lint.log
(timeout 900 make check-client 2>&1; git status --porcelain; git diff --exit-code --stat; echo "exit $?") > $L/client.log
(gitleaks git --log-opts="origin/candidate..HEAD" . 2>&1; echo "exit $?"; timeout 900 make audit 2>&1; echo "exit $?") > $L/sec.log
(timeout 1800 make test-frontend 2>&1; echo "exit $?") > $L/fe.log
for i in $(seq 720); do l=$(cut -d" " -f1 /proc/loadavg); [ $(pgrep -fc "bin/pytest") -le 0 ] && awk -v l=$l "BEGIN{exit !(l<6)}" && break; sleep 30; done; echo "load at start $(cat /proc/loadavg)" >> $L/gate.txt; echo "gate waited $i" >> $L/gate.txt
docker rm -f rag0705-evpg rag0705-evredis rag0705-evrustfs >/dev/null 2>&1
docker run -d --name rag0705-evpg -p 47055:5432 -e POSTGRES_USER=studio -e POSTGRES_PASSWORD=studio -e POSTGRES_DB=studio pgvector/pgvector:0.8.1-pg16 >/dev/null
docker run -d --name rag0705-evredis -p 47056:6379 redis:7.4.2-alpine >/dev/null
docker run -d --name rag0705-evrustfs -p 47057:9000 -e RUSTFS_ACCESS_KEY=studio -e RUSTFS_SECRET_KEY=studio-secret rustfs/rustfs:1.0.4 >/dev/null
for i in $(seq 60); do docker exec rag0705-evpg pg_isready -U studio >/dev/null 2>&1 && break; sleep 2; done; sleep 3
docker exec rag0705-evpg psql -U studio -c "CREATE DATABASE studio_test" >/dev/null
(timeout 6000 make test-backend TEST_WORKERS=3 2>&1 | grep --line-buffered -Eav "$F"; echo "exit ${PIPESTATUS[0]}") > $L/be.log
docker rm -f rag0705-evpg rag0705-evredis rag0705-evrustfs >/dev/null 2>&1
df -h / | tail -1 > $L/df.txt
docker builder prune -af >/dev/null 2>&1; df -h / | tail -1 >> $L/df.txt
(timeout 3600 bash $E/build.sh "$PWD" 0705 2>&1; echo "exit $?") > $L/images.log
free=$(df -BG --output=avail / | tail -1 | tr -dc 0-9); [ "$free" -lt 8 ] && docker builder prune -af >/dev/null 2>&1
for i in $(seq 180); do l=$(cut -d' ' -f1 /proc/loadavg); m=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo); awk -v l=$l 'BEGIN{exit !(l<7)}' && [ $m -ge 4 ] && break; sleep 20; done
set -a; source $E/e2e.env; set +a; export CI=1; C="docker compose -p rag0705-e2e -f docker-compose.yml -f $E/compose.sandbox.yml"
(timeout 3000 make e2e COMPOSE="$C" 2>&1; echo "exit $?") > $L/e2e.log 2>&1
$C down -v > /dev/null 2>&1
docker rmi rag-agent-studio/api:0705 rag-agent-studio/studio:0705 >/dev/null 2>&1
for f in install lint client sec fe be images e2e; do echo "$f: $(grep -a '^exit' $L/$f.log | tr '\n' ' ')"; done
echo ALLDONE
