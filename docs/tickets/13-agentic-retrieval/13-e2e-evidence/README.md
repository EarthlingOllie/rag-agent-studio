# Spec 13: the compose-stack end-to-end suite

The tickets in spec 13 ran their e2e specs through lint, typecheck and `pnpm e2e --list`, but not against the stack. This run closes that gap for the whole spec. It ran on the integration branch `claude/gallant-euler-zxqfxb` once all nine tickets had merged (`63abf37d`), with the fixes below in `5cf17da7`.

## Result

**121 passed, 0 failed, 0 skipped, 0 flaky** across both Playwright projects (`harness` and `studio`), with no retries. Log: [e2e.log](e2e.log).

## Command

The steps are the same as spec 12's run ([12-e2e-evidence](../../12-reskin-fixes-sidebar-navigation/12-e2e-evidence/README.md)), with this folder's copies of [build.sh](build.sh) and [compose.e2e.yml](compose.e2e.yml). The project is `rag13e2e` and the images are tagged `13e2e`:

```sh
docs/tickets/13-agentic-retrieval/13-e2e-evidence/build.sh "$PWD" 13e2e
C="docker compose -p rag13e2e -f docker-compose.yml -f docs/tickets/13-agentic-retrieval/13-e2e-evidence/compose.e2e.yml"
$C up -d --no-build --wait
make seed COMPOSE="$C"                        # make seed-reset before a rerun
cd frontend && PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome pnpm e2e --trace off
```

The images bundle the local models (`BUNDLE_MODELS=true`). Every Agentic reply in the suite comes from the Demo model or the Naive demo model. No real Anthropic or OpenAI model was called, because this sandbox has no provider key; the live-suite gap is recorded in the 13-07 and 13-09 evidence.

## Failures and fixes

Run 1 ([e2e-run1-3-failed.log](e2e-run1-3-failed.log)): 118 passed, 3 failed. Each failure was reproduced on its own, fixed, and passed on its own before the final full run, which started from a fresh seed.

| Spec | Symptom | Cause | Fix |
| --- | --- | --- | --- |
| `bulk-rollout` | axe colour-contrast violation on the dialog's Done button, with a different ratio each run (2.98, 4.26) | An app bug. When a bulk publish or revert succeeds, the footer swaps Not now and Publish/Revert for one Done button. Done had no key, so React reused the Not now `<button>` and only changed its classes. `transition-colors` then faded it over about 150ms from Not now's white to the accent colour, so it really was low contrast for that moment. | `BulkRollout.tsx`: `key="done"` on both Done buttons, so each is drawn new at its final colours. `BulkRollout.test.tsx` checks that Not now is gone after success; these checks failed before the fix. The axe assertion is unchanged |
| `models`, `playground` | `getByRole('group', { name: 'Supports tools: …' })` found no elements | A bug in the spec's locator, from 13-03. Chrome exposes the `<optgroup>`s as named groups. Playwright's role engine (1.64.1) doesn't name an optgroup from its `label`, and doesn't treat one inside a closed `<select>` as visible | The specs find each group with `locator('optgroup[label="…"]')` and still check which models are in it. The rest of each test now runs and passes |

No test was skipped, disabled, quarantined or given a longer timeout.
