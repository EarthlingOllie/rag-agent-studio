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

## Rerun after 13-10 (Agentic answers stream word by word)

13-10 merged at `9208a94b`, on top of the spec 12 CI fixes. The images were rebuilt from that tree, and the suite ran on a fresh seed: **122 passed, 0 failed, 0 skipped, 0 flaky**, with no retries. 13-10 added one test (122 rather than 121). Log: [e2e-after-13-10.log](e2e-after-13-10.log). At the same tree the backend passed 2635 tests at 100% coverage, and ruff, mypy, the frontend checks, `make check-client` and `make link-check` all passed.

Four earlier full runs on this tree had failures (`accessibility` in all four, plus `auth`, `bedrock-credentials` and `agent-revert` once or twice). The cause was this sandbox's disk, not the code:

- Playwright starts Chromium with `--disable-dev-shm-usage`, so each renderer keeps its shared memory in files under `/tmp`, about 230MB per navigation until Chrome frees them.
- The image build had left about 5GB of Docker build cache, so usable space fell to about 1MB partway through the run, and the page then open stopped rendering. `accessibility.spec.ts` opens every signed-in page twice, which is why it always hit this.
- The same failure happened with 13-10's Studio files swapped back to their `b848fc16` versions in the running container, so 13-10 didn't cause it.
- After `docker builder prune -f`, usable space was about 7GB, and `accessibility.spec.ts` passed three times out of three, twice on a fresh seed. The full run above then passed. No code changed.

When rerunning here, prune the build cache after building the images.
