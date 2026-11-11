# Merge origin/candidate (d79dd3f) into candidate-reskin (8e94ace)

- Merge base: 6a9decd. candidate ahead by 73 commits, candidate-reskin ahead by 8.
- Textual conflicts: 0.
- Files changed on both sides: GLOSSARY.md only. Auto-merged: reskin's new **Appearance** entry kept alongside candidate's glossary changes; no conflict markers; result equals candidate's GLOSSARY plus the Appearance entry.
- backend/ is byte-identical to origin/candidate after the merge (reskin never touched backend).

## Checks (in the merge worktree)
- frontend: pnpm install --frozen-lockfile, lint, typecheck, test (coverage gate), build, check-embed-size: all pass.
- make link-check: pass (2088 links, 219 files).
- Backend tests (make test-backend): not run, Docker daemon unavailable for Postgres/Redis; backend tree is identical to origin/candidate, so the merge cannot have changed its result.
