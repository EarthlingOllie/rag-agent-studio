#!/bin/sh
# Ticket 12-05 checks, from the repository root. Each log's first line names its command and
# commit. The backend and the compose-stack e2e suite are not run: this ticket changes no backend
# code and there is no compose stack in the sandbox; the changed e2e specs are linted and
# type-checked (make lint-frontend) and listed. shots.test.ts stands in for the axe sweep against
# the built Studio (see README); it needs `pnpm build`, so it runs after it.
set -u
E=docs/tickets/12-reskin-fixes-sidebar-navigation/12-05-evidence
SHA=$(git rev-parse --short HEAD)
run() { log=$1; shift; { echo "\$ $* (at $SHA)"; "$@"; echo "exit $?"; } >"$E/$log" 2>&1; tail -1 "$E/$log"; }
run install.log sh -c 'cd frontend && pnpm install --frozen-lockfile'
run lint.log make lint-frontend
run frontend-tests.log make test-frontend
run build.log sh -c 'cd frontend && pnpm build'
run link-check.log make link-check
run e2e-list.log sh -c 'cd frontend && pnpm exec playwright test --project=studio --list e2e/tests/invites.spec.ts e2e/tests/members.spec.ts e2e/tests/credentials.spec.ts e2e/tests/projects.spec.ts e2e/tests/require-mfa.spec.ts'
mkdir -p "$E/screenshots"
run shots.log sh -c "cd frontend && SHOTS_DIR=../$E/screenshots pnpm exec vitest run --config ../$E/shots.config.mjs"
