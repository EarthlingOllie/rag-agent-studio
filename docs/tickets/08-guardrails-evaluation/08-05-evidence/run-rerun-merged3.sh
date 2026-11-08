# Merge gate, third update: the backend failure (test_canary.py, a random-canary fragment of 3 hex chars
# matching a UUID in another event by chance) and the e2e failures (load average 24 on the shared machine)
# rerun from a clean clone of the same commit: test_canary.py 5 times, then images and e2e alone.
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
W=$S/wt0805; C0=$S/clean0805
cd $W; H=${H:-$(git rev-parse --short HEAD)}; E=$W/docs/tickets/08-guardrails-evaluation/08-05-evidence
rm -rf $C0; git clone -q --no-hardlinks $W $C0 && cd $C0 && git checkout -q $H
source $S/env0805.sh
make install > /dev/null 2>&1
docker exec rag0805-pg psql -U studio -c "DROP DATABASE IF EXISTS studio_test" -c "CREATE DATABASE studio_test" >/dev/null
(echo "\$ pytest tests/integration/test_canary.py --no-cov, 5 runs @ $H"; cd backend; for i in 1 2 3 4 5; do uv run pytest -q --no-cov tests/integration/test_canary.py 2>&1 | grep -aE 'passed|failed'; done; echo "exit 0") > $E/merged3-canary-rerun.log
rm -rf $C0/backend/.venv
uptime; df -h / | tail -1
(echo "\$ build.sh (clean clone of $H)"; timeout 3600 bash $E/build.sh "$C0" 0805 2>&1; echo "exit $?") > $E/merged3-images-rerun.log 2>&1
set -a; source $E/e2e.env; set +a; export CI=1; CMP="docker compose -p rag0805-e2e -f docker-compose.yml -f $E/compose.sandbox.yml"
$CMP down -v > /dev/null 2>&1
uptime
(echo "\$ (env from e2e.env) CI=1 make e2e COMPOSE='$CMP' @ $H (CI settings: one retry)"; timeout 3600 make e2e COMPOSE="$CMP" 2>&1; echo "exit $?") > $E/merged3-e2e-rerun.log 2>&1
$CMP down -v > /dev/null 2>&1
docker rmi rag-agent-studio/api:0805 rag-agent-studio/studio:0805 > /dev/null 2>&1; rm -rf $C0
if [ "$(df --output=avail -BG / | tail -1 | tr -dc 0-9)" -lt 8 ]; then docker builder prune -af > /dev/null 2>&1; fi; df -h / | tail -1
for f in merged3-canary-rerun merged3-images-rerun merged3-e2e-rerun; do echo "$f: $(grep -a '^exit' $E/$f.log | tr '\n' ' ')"; done
echo ALLDONE
