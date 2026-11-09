set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
L=$S/evalH0705-logs; D=$S/evalA0705; cd $D; E=docs/tickets/07-feedback-logging-comparison/07-05-evidence
mv $L/images.log $L/images-attempt1-enospc.log 2>/dev/null
(echo "+ retry after attempt 1 hit ENOSPC on the shared disk"; df -h / | tail -1; timeout 3600 bash $E/build.sh "$PWD" 0705 2>&1; echo "exit $?") > $L/images.log
docker builder prune -af >/dev/null 2>&1
grep -aq '^exit 0' $L/images.log || { echo IMAGESFAIL; exit 1; }
for i in $(seq 180); do l=$(cut -d' ' -f1 /proc/loadavg); m=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo); awk -v l=$l 'BEGIN{exit !(l<7)}' && [ $m -ge 4 ] && break; sleep 20; done
set -a; source $E/e2e.env; set +a; export CI=1; C="docker compose -p rag0705-e2e -f docker-compose.yml -f $E/compose.sandbox.yml"
(timeout 3000 make e2e COMPOSE="$C" 2>&1; echo "exit $?") > $L/e2e.log 2>&1
$C down -v > /dev/null 2>&1
docker rmi rag-agent-studio/api:0705 rag-agent-studio/studio:0705 >/dev/null 2>&1
for f in images e2e; do echo "$f: $(grep -a '^exit' $L/$f.log | tr '\n' ' ')"; done
echo ALLDONE
