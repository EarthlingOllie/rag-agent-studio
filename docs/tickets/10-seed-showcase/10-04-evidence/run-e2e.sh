# Sandbox `make images` and `make e2e` for 10-04 (compose project rag1004-e2e), then cleanup.
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
C=${C:-$S/wt1004}; L=${L:-$S/ev1004-logs}; mkdir -p $L; E=docs/tickets/10-seed-showcase/10-04-evidence
cd $C; SHA=$(git rev-parse --short HEAD)
H="@ $SHA (ticket/10-04-attack-panel in $(basename $C), clean tree: $(git status --porcelain | wc -l) changes)"
df -h / | tail -1 > $L/df-before-images
# SKIP_BUILD=1 reuses images this script built for the same commit (kept after a failed run).
if [ "${SKIP_BUILD:-0}" != 1 ]; then
  (echo "\$ $E/build.sh (sandbox make images) $H"; bash $E/build.sh $C 1004 2>&1; echo "exit $?") > $L/images.log
fi
set -a; . $E/e2e.env; set +a
COMPOSE="docker compose -p rag1004-e2e -f docker-compose.yml -f $E/compose.sandbox.yml"
SPECS="${SPECS:-tests/attack-panel.spec.ts tests/demo-pages.spec.ts tests/seed.spec.ts tests/embed.spec.ts tests/token-budget.spec.ts tests/llm-classifier.spec.ts tests/playground.spec.ts tests/widget-accessibility.spec.ts tests/smoke.spec.ts}"
(echo "\$ (env from e2e.env) CI=1: $COMPOSE up -d --build --wait; make seed COMPOSE=...; cd frontend && pnpm e2e $SPECS $H (CI settings: one retry)"
 $COMPOSE up -d --build --wait 2>&1 && make seed COMPOSE="$COMPOSE" 2>&1 && (cd frontend && CI=1 timeout 3600 pnpm e2e $SPECS 2>&1); echo "exit $?") > $L/e2e.log
$COMPOSE logs --no-color api worker beat host > $S/e2e1004-services.log 2>&1
$COMPOSE down -v >/dev/null 2>&1
if grep -aq '^exit 0' $L/e2e.log; then
  docker rmi rag-agent-studio/api:1004 rag-agent-studio/studio:1004 >/dev/null 2>&1
fi
docker builder prune -af >/dev/null 2>&1
echo "images: $(grep -a '^exit' $L/images.log) e2e: $(grep -a '^exit' $L/e2e.log)"
