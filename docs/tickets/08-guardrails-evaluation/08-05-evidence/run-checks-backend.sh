# After f00e4e7 (a backend test's environment only): install, lint and the backend suite again
# from a clean clone. Frontend, client, live, images and e2e are unaffected (logs at 173dd4f).
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
W=$S/wt0805; C0=$S/clean0805
cd $W; H=$(git rev-parse --short HEAD); E=$W/docs/tickets/08-guardrails-evaluation/08-05-evidence
rm -rf $C0; git clone -q --no-hardlinks $W $C0 && cd $C0 && git checkout -q $H
source $S/env0805.sh
(echo "\$ make install (clean clone of $H)"; timeout 1800 make install 2>&1 | tail -15; echo "exit ${PIPESTATUS[0]}") > $E/install-$H.log
(echo "\$ make lint @ $H"; timeout 1800 make lint 2>&1 | grep -v UV_NATIVE_TLS; echo "exit ${PIPESTATUS[0]}") > $E/lint-$H.log
docker exec rag0805-pg psql -U studio -c "DROP DATABASE IF EXISTS studio_test" -c "CREATE DATABASE studio_test" >/dev/null
(echo "\$ make test-backend (TEST_* -> rag0805-pg/redis/rustfs) @ $H"; timeout 6000 make test-backend 2>&1 | grep -vE '^\{"' ; echo "exit ${PIPESTATUS[0]}") > $E/backend-tests.log
rm -rf $C0
for f in install-$H lint-$H backend-tests; do echo "$f: $(grep -a '^exit' $E/$f.log | tr '\n' ' ')"; done
echo ALLDONE
