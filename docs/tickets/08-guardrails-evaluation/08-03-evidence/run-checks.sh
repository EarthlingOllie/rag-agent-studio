# Every check, one at a time, from a clean clone of the branch's HEAD (sandbox paths).
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
W=$S/wt0803; C0=$S/clean0803
cd $W; H=$(git rev-parse --short HEAD); E=$W/docs/tickets/08-guardrails-evaluation/08-03-evidence
rm -rf $C0; git clone -q --no-hardlinks $W $C0 && cd $C0 && git checkout -q $H
source $S/env0803.sh
(echo "\$ make install (clean clone of $H)"; timeout 1800 make install 2>&1 | tail -15; echo "exit ${PIPESTATUS[0]}") > $E/install.log
(echo "\$ make lint @ $H"; timeout 1800 make lint 2>&1 | grep -v UV_NATIVE_TLS; echo "exit ${PIPESTATUS[0]}") > $E/lint.log
(echo "\$ make test-frontend @ $H"; timeout 1800 make test-frontend 2>&1; echo "exit $?") > $E/frontend-tests.log
(echo "\$ make check-client @ $H"; timeout 900 make check-client 2>&1; echo "exit $?") > $E/client-drift.log
(echo "\$ gitleaks git (origin/candidate..HEAD) @ $H"; cd $W; gitleaks git --log-opts="origin/candidate..HEAD" --no-banner . 2>&1; echo "exit $?"; cd $C0; echo "\$ make audit @ $H"; timeout 900 make audit 2>&1 | grep -v UV_NATIVE_TLS; echo "exit ${PIPESTATUS[0]}") > $E/security.log
docker exec rag0803-pg psql -U studio -d postgres -c "DROP DATABASE IF EXISTS studio_test" -c "CREATE DATABASE studio_test" >/dev/null
(echo "\$ make test-backend (TEST_* -> rag0803-pg/redis/rustfs) @ $H"; timeout 7000 make test-backend 2>&1 | grep --line-buffered -vE '^\{"' ; echo "exit ${PIPESTATUS[0]}") > $E/backend-tests.log
(echo "\$ build.sh (sandbox make images) @ $H"; df -h / | tail -1) > $E/images.log
(timeout 3000 bash $E/build.sh "$C0" 0803 >> $E/images.log 2>&1; echo "exit $?" >> $E/images.log)
set -a; source $E/e2e.env; set +a; export CI=1; CMP="docker compose -p rag0803-e2e -f docker-compose.yml -f $E/compose.sandbox.yml"
$CMP down -v > /dev/null 2>&1
(echo "\$ (env from e2e.env) CI=1 make e2e COMPOSE='$CMP' @ $H (CI settings: one retry)"; timeout 2700 make e2e COMPOSE="$CMP" 2>&1; echo "exit $?") > $E/e2e.log 2>&1
$CMP down -v > /dev/null 2>&1
for f in install lint frontend-tests client-drift security backend-tests images e2e; do echo "$f: $(grep -a '^exit' $E/$f.log | tr '\n' ' ')"; done
echo ALLDONE
