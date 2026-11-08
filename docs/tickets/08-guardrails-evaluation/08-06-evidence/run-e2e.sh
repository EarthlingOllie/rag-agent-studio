#!/usr/bin/env bash
# Images, the end-to-end suite and the Block rate alert in the running stack, from a clean
# checkout C of this branch; logs go to L. Sandbox-only: compose project rag0806-e2e on host
# ports 49610-49689, images built by build.sh (07-04's: committed Dockerfiles plus the egress CA).
# SKIP_IMAGES=1 reuses images this script already built for the same commit.
set -u
C=$1; L=$2; mkdir -p $L; E=docs/tickets/08-guardrails-evaluation/08-06-evidence
cd $C; SHA=$(git rev-parse --short HEAD)
H="@ $SHA (clean tree: $(git status --porcelain | wc -l) changes)"
df -h / | tail -1 > $L/df-before-images
[ "${SKIP_IMAGES:-0}" = 1 ] || (echo "\$ $E/build.sh $H"; bash $E/build.sh $C 0806 2>&1; echo "exit $?") > $L/images.log
set -a; . $E/e2e.env; set +a
COMPOSE="docker compose -p rag0806-e2e -f docker-compose.yml -f $E/compose.sandbox.yml"
(echo "\$ (env from e2e.env) CI=1 make e2e COMPOSE='$COMPOSE' $H (CI settings: one retry)"; CI=1 timeout 3600 make e2e COMPOSE="$COMPOSE" 2>&1; echo "exit $?") > $L/e2e.log
(echo "\$ spike_in_stack.py in the stack's API container $H"; $COMPOSE cp $E/spike_in_stack.py api:/tmp/spike_in_stack.py && $COMPOSE exec -T api python /tmp/spike_in_stack.py 2>&1 | grep -vE '^\{"'; echo "exit ${PIPESTATUS[0]}") > $L/spike-in-stack.log
$COMPOSE down -v >/dev/null 2>&1
docker rmi rag-agent-studio/api:0806 rag-agent-studio/studio:0806 >/dev/null 2>&1
docker builder prune -af >/dev/null 2>&1
for f in images e2e spike-in-stack; do echo "$f: $(grep -a "^exit" $L/$f.log | tr "\n" " ")"; done
