#!/usr/bin/env bash
# Runs every check for ticket 03-10 sequentially in a fresh clone of the pushed branch, one log
# each, into this evidence folder. $1 = the clone's directory.
set -u
CLONE=$1
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
. $S/env0310.sh
cd "$CLONE"
E=docs/tickets/03-projects-knowledge-base/03-10-evidence
SHA=$(git rev-parse --short HEAD)
run() { local log=$1; shift; { echo "\$ $* @ $SHA"; "$@"; echo "exit $?"; } > "$E/$log" 2>&1; }
docker exec rag0310-pg psql -U studio -q -c 'drop database if exists studio_test' -c 'create database studio_test'
run install.log make install
run lint.log make lint
run backend-tests.log make test-backend
run frontend-tests.log make test-frontend
run client-drift.log make check-client
run images.log bash "$E/build.sh" "$CLONE" 0310
C="docker compose -p rag0310 -f docker-compose.yml -f $E/compose.sandbox.yml"
$C down -v >/dev/null 2>&1
set -a; . "$E/e2e.env"; set +a
run e2e.log make e2e COMPOSE="$C"
$C down -v >/dev/null 2>&1
echo ALLDONE > $S/checks0310.done
