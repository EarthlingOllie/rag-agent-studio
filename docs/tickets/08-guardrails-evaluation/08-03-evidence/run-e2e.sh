# Rerun of the e2e step alone (after attempt 1 hit a host port held by another process), in the
# same clean clone and with the images run-checks.sh built, on host ports outside the ephemeral range.
set -u
S=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
W=$S/wt0803; C0=$S/clean0803; E=$W/docs/tickets/08-guardrails-evaluation/08-03-evidence
cd $C0; H=$(git rev-parse --short HEAD)
set -a; source $E/e2e.env; set +a; export CI=1; CMP="docker compose -p rag0803-e2e -f docker-compose.yml -f $E/compose.sandbox.yml"
$CMP down -v > /dev/null 2>&1
(echo "\$ (env from e2e.env) CI=1 make e2e COMPOSE='$CMP' @ $H (CI settings: one retry)"; timeout 3600 make e2e COMPOSE="$CMP" 2>&1; echo "exit $?") > $E/e2e.log 2>&1
$CMP down -v > /dev/null 2>&1
echo "e2e: $(grep -a '^exit' $E/e2e.log)"; echo ALLDONE
