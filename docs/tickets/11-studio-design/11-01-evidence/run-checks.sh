#!/bin/sh
# Ticket 11-01 checks, from the repository root of a clean checkout. Each log's first line names
# its command and commit. Backend and e2e are not run: this ticket changes no backend code and no
# page (the new components are not used by any route yet); see the evidence README.
set -u
E=docs/tickets/11-studio-design/11-01-evidence
SHA=$(git rev-parse --short HEAD)
run() { log=$1; shift; { echo "\$ $* (at $SHA)"; "$@"; echo "exit $?"; } >"$E/$log" 2>&1; tail -1 "$E/$log"; }
run install.log sh -c 'cd frontend && pnpm install --frozen-lockfile'
run lint.log make lint-frontend
run frontend-tests.log make test-frontend
run build.log sh -c 'cd frontend && pnpm build'
run link-check.log make link-check
# The ratchet on the real tree: a rise fails, then the tree is put back.
{
  echo "\$ palette ratchet rise demo (at $SHA): add one palette class to a Studio file, run, revert"
  printf '\nexport const RATCHET_DEMO = "bg-slate-700";\n' >> frontend/apps/studio/src/design/recipes.ts
  (cd frontend && node scripts/palette-ratchet/cli.mjs); echo "exit $?"
  git checkout -- frontend/apps/studio/src/design/recipes.ts
  (cd frontend && node scripts/palette-ratchet/cli.mjs); echo "exit $?"
} >"$E/ratchet-rise-demo.log" 2>&1
tail -1 "$E/ratchet-rise-demo.log"
