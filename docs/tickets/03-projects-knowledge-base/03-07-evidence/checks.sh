#!/usr/bin/env bash
# Runs every check for ticket 03-07 sequentially, one log each, into the evidence folder.
cd /tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad && . ./env0307.sh
cd wt-0307
E=docs/tickets/03-projects-knowledge-base/03-07-evidence
SHA=$(git rev-parse --short HEAD)
run() { local log=$1; shift; { echo "\$ $* @ $SHA"; "$@"; echo "exit $?"; } > "$E/$log" 2>&1; }
docker exec rag0307-postgres-1 psql -U studio -q -c 'drop database if exists studio_test' -c 'create database studio_test'
run backend-tests.log make test-backend
run frontend-tests.log make test-frontend
run lint.log make lint
run client-drift.log make check-client
run security.log make secret-scan audit
C="docker compose -p rag0307 -f docker-compose.yml -f $E/compose.sandbox.yml"
$C down -v >/dev/null 2>&1
set -a; . $E/e2e.env; set +a
run e2e.log make e2e COMPOSE="$C"
echo ALLDONE > ../checks0307.done
