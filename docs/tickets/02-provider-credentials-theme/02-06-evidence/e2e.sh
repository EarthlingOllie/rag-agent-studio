#!/usr/bin/env bash
# The e2e run: compose up --wait (project rag0206, sandbox ports and images from build.sh), then the full Playwright suite.
set -u
CLONE=$1; EV=$(cd "$(dirname "$0")" && pwd)
set -a; . "$EV/e2e.env"; set +a
cd "$CLONE"
docker compose -p rag0206 -f docker-compose.yml -f "$EV/compose.sandbox.yml" up -d --wait || exit 1
cd frontend
pnpm e2e
