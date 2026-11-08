#!/usr/bin/env bash
# Every check for 08-07, one after another, from a fresh clone of the branch head. Logs land
# beside this script; each log's first line names the command and commit. Sandbox specifics:
# backend services are rag0807-pg/redis/rustfs containers; the e2e stack is compose project
# rag0807-e2e with images from 08-05's build.sh (committed Dockerfiles + the egress CA) and the
# host ports moved by compose0807.yml.
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
W=$S/wt0807; C0=$S/clean0807; E=$W/docs/tickets/08-guardrails-evaluation/08-07-evidence
cd $W; H=$(git rev-parse --short HEAD)
export TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:47852/studio_test
export TEST_REDIS_URL=redis://localhost:45879/15
export TEST_OBJECT_STORE_URL=http://localhost:45891
export HF_HOME=$S/hf-cache HF_HUB_DISABLE_XET=1
log() { local name=$1; shift; (echo "\$ $* @ $H"; timeout 7000 "$@" 2>&1 | grep -avE '^\{"|UV_NATIVE_TLS'; echo "exit ${PIPESTATUS[0]}") > $E/$name.log; }
rm -rf $C0; git clone -q --no-hardlinks $W $C0 && cd $C0 && git checkout -q $H || exit 1
log install make install
log lint make lint
log eval-mocked make eval
# The CI command with a weaker input classifier swapped in (the heuristic baseline): must fail.
log eval-weakened-defence bash -c "cd backend && uv run python -m app.evals --mode mocked --classifier heuristic --out $C0/r-weak"
log eval-live-demo make eval-live EVAL_PROVIDER=demo EVAL_MODEL=demo EVAL_OUT=$C0/backend/eval-report-live
log eval-live-below-minimum make eval-live EVAL_PROVIDER=demo EVAL_MODEL=demo EVAL_MIN_PASS_RATE=0.95 EVAL_OUT=$C0/r-below
rm -rf $E/eval-report-mocked $E/eval-report-live-demo
cp -r $C0/backend/eval-report $E/eval-report-mocked; cp -r $C0/backend/eval-report-live $E/eval-report-live-demo
log client-drift make check-client
log frontend-tests make test-frontend
docker exec rag0807-pg psql -U studio -c "DROP DATABASE IF EXISTS studio_test" -c "CREATE DATABASE studio_test" >/dev/null
log backend-tests make test-backend
log security gitleaks git --redact --no-banner --log-opts="origin/candidate..HEAD" .
# Images and end-to-end
df -h / | tail -1 > $E/disk-before-images.txt
log images bash $C0/docs/tickets/08-guardrails-evaluation/08-05-evidence/build.sh $C0 0807
set -a; source $S/e2e0807.env; set +a; export CI=1
CMP="docker compose -p rag0807-e2e -f docker-compose.yml -f $S/compose0807.yml"
$CMP down -v > /dev/null 2>&1
log e2e make e2e COMPOSE="$CMP"
$CMP down -v > /dev/null 2>&1
docker rmi rag-agent-studio/api:0807 rag-agent-studio/studio:0807 > /dev/null 2>&1
cd $S; rm -rf $C0
for f in $E/*.log; do echo "$(basename $f): $(grep -a '^exit' $f | tr '\n' ' ')"; done
echo ALLDONE
