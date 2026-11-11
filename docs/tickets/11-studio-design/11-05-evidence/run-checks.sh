#!/bin/sh
# Ticket 11-05 checks, from the repository root of a clean checkout. Each log's first line names
# its command and commit. The backend and the compose-stack e2e suite are not run: this ticket
# changes no backend code, and there is no Docker daemon in the sandbox. The Playwright harness
# (which checks the navigation helpers) runs in Chrome, and shots.test.ts stands in for the axe
# harness (see README).
set -u
E=docs/tickets/11-studio-design/11-05-evidence
SHA=$(git rev-parse --short HEAD)
run() { log=$1; shift; { echo "\$ $* (at $SHA)"; "$@"; echo "exit $?"; } >"$E/$log" 2>&1; tail -1 "$E/$log"; }
run install.log sh -c 'cd frontend && pnpm install --frozen-lockfile'
run lint.log make lint-frontend
run frontend-tests.log make test-frontend
run build.log sh -c 'cd frontend && pnpm build'
run link-check.log make link-check
run e2e-harness.log sh -c 'cd frontend && PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome pnpm e2e:harness'
mkdir -p "$E/screenshots"
run shots.log sh -c "cd frontend && SHOTS_DIR=../$E/screenshots pnpm exec vitest run --config ../$E/shots.config.mjs"
