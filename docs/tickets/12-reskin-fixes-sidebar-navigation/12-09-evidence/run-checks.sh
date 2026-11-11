#!/bin/sh
# Ticket 12-09 checks, from the repository root of a clean checkout. Each log's first line names
# its command and commit. The backend tests are not run: this ticket changes no backend code. There
# is no Docker daemon in this sandbox, so the compose-stack specs are listed (they parse and
# type-check) rather than run; the harness project runs, and shots.test.ts stands in for the axe
# sweep and the keyboard pass against the built Studio (see README); it builds on `pnpm build`.
set -u
E=docs/tickets/12-reskin-fixes-sidebar-navigation/12-09-evidence
SHA=$(git rev-parse --short HEAD)
run() { log=$1; shift; { echo "\$ $* (at $SHA)"; "$@"; echo "exit $?"; } >"$E/$log" 2>&1; tail -1 "$E/$log"; }
run install.log sh -c 'cd frontend && pnpm install --frozen-lockfile'
run lint.log make lint-frontend
run frontend-tests.log make test-frontend
run build.log sh -c 'cd frontend && pnpm build'
run link-check.log make link-check
run e2e-harness.log sh -c 'cd frontend && PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome pnpm e2e:harness'
run e2e-list.log sh -c 'cd frontend && pnpm exec playwright test --project=studio --list e2e/tests/sidebar.spec.ts e2e/tests/accessibility.spec.ts'
mkdir -p "$E/screenshots"
run shots.log sh -c "cd frontend && SHOTS_DIR=../$E/screenshots pnpm exec vitest run --config ../$E/shots.config.mjs"
