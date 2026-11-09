# Sandbox `make images`, the seed as the ECS seed task runs it, and `make e2e` for 10-05 (compose project
# rag1005-e2e), then cleanup.
# The ECS-like seed: the seed task's command (`python -m app.seed`) in the API image with NO seed folder mounted,
# so it reads the demo Documents the image carries at /seed, on a fresh database; then again, to show that a second
# run changes no counts. Then `make seed` (the mounted local path) and the full Playwright suite, as `make e2e` does.
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
C=${C:-$S/wt1005}; L=${L:-$S/ev1005-logs}; mkdir -p $L; E=docs/tickets/10-seed-showcase/10-05-evidence
cd $C; SHA=$(git rev-parse --short HEAD)
H="@ $SHA ($(git rev-parse --abbrev-ref HEAD) in $(basename $C), clean tree: $(git status --porcelain | wc -l) changes)"
df -h / | tail -1 > $L/df-before-images
# This machine is shared: free the build cache first when under 8 GB are left.
[ "$(df --output=avail -BG / | tail -1 | tr -dc 0-9)" -ge 8 ] || docker builder prune -af >/dev/null 2>&1
if [ "${SKIP_BUILD:-0}" != 1 ]; then
  (echo "\$ $E/build.sh (sandbox make images) $H"; bash $E/build.sh $C 1005 2>&1; echo "exit $?") > $L/images.log
fi
set -a; . $E/e2e.env; set +a
COMPOSE="docker compose -p rag1005-e2e -f docker-compose.yml -f $E/compose.sandbox.yml"
counts() {
  $COMPOSE exec -T postgres psql -U studio -d studio -At -F ' ' -c "SELECT
    (SELECT count(*) FROM organisations) AS organisations, (SELECT count(*) FROM members) AS members,
    (SELECT count(*) FROM projects) AS projects, (SELECT count(*) FROM documents) AS documents,
    (SELECT count(*) FROM tags) AS tags, (SELECT count(*) FROM agents) AS agents,
    (SELECT count(*) FROM agent_versions) AS agent_versions,
    (SELECT count(*) FROM project_instructions_versions) AS instructions_versions,
    (SELECT count(*) FROM conversations) AS conversations, (SELECT count(*) FROM messages) AS messages,
    (SELECT count(*) FROM message_feedback) AS feedback, (SELECT count(*) FROM conversation_ratings) AS ratings,
    (SELECT count(*) FROM audit_events) AS audit_events, (SELECT count(*) FROM provider_credentials) AS credentials"
}
ECS_SEED="$COMPOSE run --rm --no-deps -e OBJECT_STORE_PUBLIC_ENDPOINT_URL=http://rustfs:9000 api python -m app.seed"
(echo "\$ (env from e2e.env) $COMPOSE up -d --wait $H"
 $COMPOSE up -d --wait 2>&1; echo "exit $?") > $L/stack-up.log
(echo "# Columns: organisations members projects documents tags agents agent_versions instructions_versions conversations messages feedback ratings audit_events credentials"
 echo "\$ counts on the fresh database"; counts
 echo "\$ $ECS_SEED   # run 1: the seed task's command, no seed folder mounted $H"
 $ECS_SEED 2>&1 | grep -Eav '^\{"(name|timestamp)"'; echo "exit ${PIPESTATUS[0]}"
 echo "\$ counts after run 1"; counts | tee $L/counts1
 echo "\$ $ECS_SEED   # run 2: the same command again"
 $ECS_SEED 2>&1 | grep -Eav '^\{"(name|timestamp)"'; echo "exit ${PIPESTATUS[0]}"
 echo "\$ counts after run 2"; counts | tee $L/counts2
 if cmp -s $L/counts1 $L/counts2; then echo "idempotent: run 2 changed no counts"; echo "exit 0"; else echo "NOT idempotent"; echo "exit 1"; fi
) > $L/ecs-seed.log
(echo "\$ CI=1: make seed COMPOSE=...; cd frontend && pnpm e2e (the full suite) $H (CI settings: one retry)"
 make seed COMPOSE="$COMPOSE" 2>&1 && (cd frontend && CI=1 timeout 3600 pnpm e2e 2>&1); echo "exit $?") > $L/e2e.log
$COMPOSE logs --no-color api worker beat host > $S/e2e1005-services.log 2>&1
$COMPOSE down -v >/dev/null 2>&1
if grep -aq '^exit 0' $L/e2e.log && [ "$(grep -ac '^exit 0' $L/ecs-seed.log)" = 3 ]; then
  docker rmi rag-agent-studio/api:1005 rag-agent-studio/studio:1005 >/dev/null 2>&1
fi
docker builder prune -af >/dev/null 2>&1
echo "images: $(grep -a '^exit' $L/images.log) ecs-seed: $(grep -a '^exit' $L/ecs-seed.log | tr '\n' ' ') e2e: $(grep -a '^exit' $L/e2e.log)"
