#!/bin/sh
# Ticket 12-08: the compose-stack end-to-end suite, from the repository root, in the sandbox.
# The sandbox's agent proxy needs its CA in the image builds and blocks plain-HTTP apt, and the
# sandbox's own Postgres and Redis hold 5432 and 6379, so the images are built from
# stack/*.Dockerfile (the repository's Dockerfiles plus the CA, minus the apt upgrade) with the
# light backend (no PDF, no bundled models) and started with stack/env-override.yml (the fake
# embedder, the heuristic classifiers, Postgres and Redis unpublished). CA_DIR holds ca-bundle.crt.
#   BASE=<dir with a checkout of 63a7569's frontend and seed> also runs the failing specs there,
#   against a Studio image built from it, to show they fail before this ticket too.
set -u
E=docs/tickets/12-reskin-fixes-sidebar-navigation/12-08-evidence
SHA=$(git rev-parse --short HEAD)
C="docker compose -f docker-compose.yml -f $E/stack/env-override.yml"
PX="--build-arg HTTP_PROXY=$HTTPS_PROXY --build-arg HTTPS_PROXY=$HTTPS_PROXY --build-arg http_proxy=$HTTPS_PROXY --build-arg https_proxy=$HTTPS_PROXY"
run() { log=$1; shift; { echo "\$ $* (at $SHA)"; "$@"; echo "exit $?"; } >"$E/$log" 2>&1; tail -1 "$E/$log"; }
export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome
run stack-up.log sh -c "docker build --network host $PX -f $E/stack/frontend.Dockerfile --build-context ca=$CA_DIR -t rag-agent-studio-studio frontend \
  && docker build --network host $PX --build-arg WITH_PDF=false --build-arg BUNDLE_MODELS=false -f $E/stack/backend.Dockerfile --build-context ca=$CA_DIR --build-context seed=seed -t rag-agent-studio-api backend \
  && for s in worker beat; do docker tag rag-agent-studio-api rag-agent-studio-\$s; done \
  && for s in widget host; do docker tag rag-agent-studio-studio rag-agent-studio-\$s; done \
  && $C up -d --no-build --wait \
  && { make seed COMPOSE='$C' >/tmp/12-08-seed.out 2>&1; rc=\$?; tail -8 /tmp/12-08-seed.out; exit \$rc; }"
CHANGED="e2e/tests/sidebar.spec.ts e2e/tests/organisation-switcher.spec.ts e2e/tests/require-mfa.spec.ts e2e/tests/mfa.spec.ts e2e/tests/auth.spec.ts e2e/tests/invites.spec.ts"
run e2e-stack-changed.log sh -c "cd frontend && pnpm exec playwright test --project=studio $CHANGED"
run e2e-stack-full.log sh -c "cd frontend && pnpm exec playwright test --project=studio"
if [ -n "${BASE:-}" ]; then
  FAILING=$(sed -n 's/^    \[studio\] › \(e2e\/tests\/[a-z-]*\.spec\.ts\):.*/\1/p' "$E/e2e-stack-full.log" | sort -u | tr '\n' ' ')
  run e2e-stack-base.log sh -c "docker build --network host $PX -f $E/stack/frontend.Dockerfile --build-context ca=$CA_DIR -t rag-agent-studio-studio $BASE/frontend \
    && $C up -d --no-build --wait studio && cd $BASE/frontend && node $PWD/frontend/node_modules/@playwright/test/cli.js test --project=studio $FAILING"
  sed -i '/CreatePlatformSocket/d' "$E/e2e-stack-base.log"
fi
