#!/bin/sh
# Ticket 12-07 checks, from the repository root of a clean checkout. Each log's first line names
# its command and commit. The backend and the compose-stack e2e suite are not run: this ticket
# changes no backend code, and there is no Docker daemon in the sandbox. The Playwright harness
# runs in Chrome, and shots.test.ts stands in for the axe harness (see README).
set -u
E=docs/tickets/12-reskin-fixes-sidebar-navigation/12-07-evidence
SHA=$(git rev-parse --short HEAD)
run() { log=$1; shift; { echo "\$ $* (at $SHA)"; "$@"; echo "exit $?"; } >"$E/$log" 2>&1; tail -1 "$E/$log"; }
run install.log sh -c 'cd frontend && pnpm install --frozen-lockfile'
# make lint-frontend and make test-frontend, one log per step
run lint.log sh -c 'cd frontend && pnpm lint'
run typecheck.log sh -c 'cd frontend && pnpm typecheck'
run test.log sh -c 'cd frontend && pnpm test'
run check-embed-size.log sh -c 'cd frontend && pnpm check-embed-size'
run palette-ratchet.log sh -c 'cd frontend && pnpm palette-ratchet'
run build.log sh -c 'cd frontend && pnpm build'
run link-check.log make link-check
run e2e-harness.log sh -c 'cd frontend && PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome pnpm e2e:harness'
mkdir -p "$E/screenshots"
run shots.log sh -c "cd frontend && SHOTS_DIR=../$E/screenshots pnpm exec vitest run --config ../$E/shots.config.mjs"
