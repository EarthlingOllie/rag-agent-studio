#!/usr/bin/env bash
# The e2e run: compose up --wait (project rag0205, sandbox ports and images), then the full Playwright suite.
set -u
CLONE=$1; EV=$(cd "$(dirname "$0")" && pwd)
cd "$CLONE"
STUDIO_URL=http://localhost:55173 docker compose -p rag0205 -f docker-compose.yml -f "$EV/compose.sandbox.yml" up -d --wait || exit 1
cd frontend
E2E_BASE_URL=http://localhost:55173 E2E_MAILPIT_URL=http://localhost:58025 PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome pnpm e2e
