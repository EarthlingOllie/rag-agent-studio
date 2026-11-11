#!/bin/sh
# Ticket 12-01 checks, from the repository root of a clean checkout. Each log's first line names
# its command and commit. The backend and the compose-stack e2e suite (including the new
# e2e/tests/select-chevron.spec.ts) are not run: this ticket changes no backend code, and there is
# no Docker daemon in the sandbox. The new spec is listed (it parses and type-checks), and
# shots.test.ts runs its check on every select of every signed-in page of the built Studio, with
# the screenshots and the axe sweep (see README); it builds on `pnpm build`, so it runs after it.
set -u
E=docs/tickets/12-reskin-fixes-sidebar-navigation/12-01-evidence
SHA=$(git rev-parse --short HEAD)
run() { log=$1; shift; { echo "\$ $* (at $SHA)"; "$@"; echo "exit $?"; } >"$E/$log" 2>&1; tail -1 "$E/$log"; }
run install.log sh -c 'cd frontend && pnpm install --frozen-lockfile'
run lint.log make lint-frontend
run frontend-tests.log make test-frontend
run build.log sh -c 'cd frontend && pnpm build'
run link-check.log make link-check
run e2e-list.log sh -c 'cd frontend && pnpm exec playwright test --project=studio --list e2e/tests/select-chevron.spec.ts'
mkdir -p "$E/screenshots"
run shots.log sh -c "cd frontend && SHOTS_DIR=../$E/screenshots pnpm exec vitest run --config ../$E/shots.config.mjs"
