# Sandbox `make images` and `make e2e` for 10-02 (compose project rag1002-e2e), then cleanup.
# The seed (`make seed`, timed) now plays the full four-week history in the real stack: worker
# ingestion, the local Embedding Model's stand-in, the local input classifier and the Demo model.
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
C=${C:?checkout}; L=${L:?log dir}; mkdir -p $L; E=docs/tickets/10-seed-showcase/10-02-evidence
cd $C; SHA=$(git rev-parse --short HEAD)
H="@ $SHA (ticket/10-02-seeded-history in $(basename $C), clean tree: $(git status --porcelain | wc -l) changes)"
df -h / | tail -1 > $L/df-before-images
if [ "${SKIP_BUILD:-0}" != 1 ]; then
  (echo "\$ $E/build.sh (sandbox make images) $H"; bash $E/build.sh $C 1002 2>&1; echo "exit $?") > $L/images.log
fi
set -a; . $E/e2e.env; set +a
COMPOSE="docker compose -p rag1002-e2e -f docker-compose.yml -f $E/compose.sandbox.yml"
SPECS="${SPECS:-tests/seed.spec.ts tests/demo-pages.spec.ts tests/embed.spec.ts tests/token-budget.spec.ts tests/operational-settings.spec.ts tests/widget-lifecycle.spec.ts tests/widget-accessibility.spec.ts tests/branded-widget.spec.ts tests/smoke.spec.ts tests/auth.spec.ts}"
(echo "\$ (env from e2e.env) CI=1: $COMPOSE up -d --build --wait; time make seed COMPOSE=...; cd frontend && pnpm e2e $SPECS $H (CI settings: one retry)"
 $COMPOSE up -d --build --wait 2>&1 && time make seed COMPOSE="$COMPOSE" 2>&1 && (cd frontend && CI=1 timeout 3600 pnpm e2e $SPECS 2>&1); echo "exit $?") > $L/e2e.log 2>&1
# What the seeded history looks like in the stack's database, for the README.
$COMPOSE exec -T postgres psql -U studio -d studio -c "SELECT a.name, v.number, count(DISTINCT c.id) AS conversations, count(m.id) AS replies FROM messages m JOIN conversations c ON c.id = m.conversation_id JOIN agents a ON a.id = c.agent_id JOIN agent_versions v ON v.id = m.agent_version_id WHERE m.role = 'assistant' AND NOT c.is_playground AND m.created_at < date_trunc('day', now()) GROUP BY 1, 2 ORDER BY 1, 2" > $L/history-in-compose.log 2>&1
$COMPOSE logs --no-color api worker beat host > $S/e2e1002-services.log 2>&1
$COMPOSE down -v >/dev/null 2>&1
if grep -aq '^exit 0' $L/e2e.log; then
  docker rmi rag-agent-studio/api:1002 rag-agent-studio/studio:1002 >/dev/null 2>&1
fi
docker builder prune -af >/dev/null 2>&1
echo "images: $(grep -a '^exit' $L/images.log) e2e: $(grep -a '^exit' $L/e2e.log)"
