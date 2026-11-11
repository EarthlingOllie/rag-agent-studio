# Sandbox `make images` and `make e2e` for 10-06 (compose project rag1006-e2e), then cleanup.
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
C=${C:-$S/wt1006}; L=${L:-$S/ev1006-logs}; mkdir -p $L; E=docs/tickets/10-seed-showcase/10-06-evidence
cd $C; SHA=$(git rev-parse --short HEAD)
H="@ $SHA (ticket/10-06-readme-demo in $(basename $C), clean tree: $(git status --porcelain | wc -l) changes)"
df -h / | tail -1 > $L/df-before-images
# SKIP_BUILD=1 reuses images this script built for the same commit (kept after a failed run).
if [ "${SKIP_BUILD:-0}" != 1 ]; then
  (echo "\$ $E/build.sh (sandbox make images) $H"; bash $E/build.sh $C 1006 2>&1; echo "exit $?") > $L/images.log
fi
set -a; . $E/e2e.env; set +a
COMPOSE="docker compose -p rag1006-e2e -f docker-compose.yml -f $E/compose.sandbox.yml"
SPECS="${SPECS:-tests/}"
(echo "\$ (env from e2e.env) CI=1: $COMPOSE up -d --build --wait; make seed COMPOSE=...; cd frontend && pnpm e2e $SPECS $H (CI settings: one retry)"
 { [ "${SKIP_UP:-0}" = 1 ] || { $COMPOSE up -d --build --wait 2>&1 && make seed COMPOSE="$COMPOSE" 2>&1; }; } && (cd frontend && CI=1 timeout 3600 pnpm e2e $SPECS 2>&1); echo "exit $?") > $L/e2e.log
$COMPOSE logs --no-color api worker beat host > $S/e2e1006-services.log 2>&1
# KEEP=1 leaves the stack up (and its images) for another SPECS run with SKIP_UP=1.
[ "${KEEP:-0}" = 1 ] && { echo "kept stack"; exit 0; }
$COMPOSE down -v >/dev/null 2>&1
if grep -aq '^exit 0' $L/e2e.log; then
  docker rmi rag-agent-studio/api:1006 rag-agent-studio/studio:1006 >/dev/null 2>&1
fi
docker builder prune -af >/dev/null 2>&1
echo "images: $(grep -a '^exit' $L/images.log) e2e: $(grep -a '^exit' $L/e2e.log)"
