set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
C=$S/wt0605; L=$S/ev0605-logs; E=docs/tickets/06-embed-widget-operational-settings/06-05-evidence
cd $C; SHA=$(git rev-parse --short HEAD)
H="@ $SHA (ticket/06-05-rate-limits, clean tree: $(git status --porcelain | wc -l) changes)"
(echo "\$ $E/build.sh (sandbox make images) $H"; bash $E/build.sh $C 0605 2>&1; echo "exit $?") > $L/images.log
set -a; . $E/e2e.env; set +a
COMPOSE="docker compose -p rag0605-e2e -f docker-compose.yml -f $E/compose.sandbox.yml"
SPECS="tests/rate-limits.spec.ts tests/embed.spec.ts tests/operational-settings.spec.ts tests/widget-lifecycle.spec.ts tests/widget-accessibility.spec.ts tests/branded-widget.spec.ts tests/playground.spec.ts tests/auth.spec.ts tests/smoke.spec.ts tests/message-feedback.spec.ts"
(echo "\$ (env from e2e.env) CI=1: $COMPOSE up -d --build --wait; make seed COMPOSE=...; cd frontend && pnpm e2e $SPECS $H (CI settings: one retry)"
 $COMPOSE up -d --build --wait 2>&1 && make seed COMPOSE="$COMPOSE" 2>&1 && (cd frontend && CI=1 timeout 3600 pnpm e2e $SPECS 2>&1); echo "exit $?") > $L/e2e.log
$COMPOSE logs --no-color api > $S/e2e0605-api.log 2>&1
$COMPOSE down -v >/dev/null 2>&1
docker rmi rag-agent-studio/api:0605 rag-agent-studio/studio:0605 >/dev/null 2>&1; docker builder prune -af >/dev/null 2>&1
echo "images: $(grep -a '^exit' $L/images.log) e2e: $(grep -a '^exit' $L/e2e.log)"; echo ALLDONE
