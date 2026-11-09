# Evidence: ticket 11-07, Instructions, Versions and rollout dialog

Branch `ticket/11-07-instructions-versions-rollout`, from `origin/candidate-reskin` at `396d100` (the merge of 11-11, #88). The claim commit `43e957a` set Status `in-progress`. Then:

- `49401c9` adds a `current` kind to `Badge`: the words "Current", on `accent-soft`. It has a test.
- `157b51b` moves the Instructions page onto the design system: the Draft and Publish panels, the Versions timeline, Compare with `Diff`, revert in a `ConfirmDialog`, the rollout and bulk-revert offers in `Dialog`s, and the Agents-behind summary as chips and badges. It also updates the unit tests and two e2e specs.
- `7b10241` updates `GLOSSARY.md` and `docs/design/README.md`.
- `cabfd34` merges `origin/candidate-reskin` at `0b65fe4` (11-12, #87, and the reskin screenshots). The only conflict was the design README's page list. Both sides were kept.
- `b51b3f9` is this folder's scripts. The last commit changes only this folder and the ticket file.

No backend code, route or permission changes. One Studio API call is gone: see *Moved actions*.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

The Instructions section (`projects/InstructionsTab.tsx`, `InstructionsVersions.tsx`, `BulkRollout.tsx`) is the heading and description, then four `surface.panel` cards, each under an h3:

- **Draft**: the markdown editor with its character count ("141 / 20000 characters"). **Save Instructions** is a `button.secondary`. "Instructions saved" is a quiet status. Refusals are `Notice tone="error"`. When someone else saved first, the conflict offer is a warning notice with **Load their changes** and **Save mine over theirs** as secondary buttons. An archived Project shows an info notice instead of the buttons.
- **Publish**: the Note field (`field.input` with a hint) and **Publish Instructions**. It is the `button.primary`, and the only one on the page.
- **Agents**: "2 Agents behind the Current Version" followed by a version chip, then **Roll out v2…** (secondary). The table is a `table.wrap` card. The Live Version is a version chip, or the **Not live** badge. Instructions is a version chip, or "None", plus an **Instructions behind** badge on each Agent that is behind.
- **Versions**: "Current Version: v2." and **Revert to v1** (secondary). The timeline lists Versions newest first. Each one has a dot on a rail, its version chip, the **Current** badge on the Current Version, the author and time, the note, and "Show the Instructions". Then comes **Compare**, an inner panel: From and To selects (`field.select`), then the design system's `Diff`. `Diff` shows both sides' line numbers, + and − marks read as "Added" and "Removed", the soft green and soft red rows, and a "2 added, 1 removed" summary. Identical sides still say "No differences: v2 and the Draft are the same."

**Revert** asks in a destructive `ConfirmDialog`. It is an alertdialog, "Revert to v1?", with the same sentence as before. Focus starts on Cancel, and the confirm button is "Yes, revert to v1". Cancel returns focus to **Revert to v1**.

**The rollout offer** (after publishing, or from **Roll out v2…**) is a modal `Dialog`, "Roll out Instructions v2". The explanation is its description. Focus starts on the first Agent, and Escape, the scrim or **Not now** close it. Every eligible Agent is pre-selected. Each row has the Agent, "Live v4, Instructions v1" as version chips (or the Not live badge), a **Draft** badge with "changes not included" (hover: "Unpublished Draft changes are not included.") when the Agent has Draft edits, and the reason when it can't be selected. **Publish to N Agents** is the dialog's primary. The results first count the outcomes ("2 succeeded, 0 skipped, 1 failed"), then list each Agent with Done, Skipped or Failed and the reason.

**The bulk-revert offer** (after reverting, when Agents are pinned to the reverted Version) is the same kind of `Dialog`, "Revert the Agents on Instructions v2?", with every Agent pre-selected, **Revert N Agents**, and the same counted results.

**States.** Loading the Instructions is `Skeleton` "Loading the Instructions". A failed load is an error `EmptyState`, "The Instructions could not be loaded". Loading the Agents is a `Skeleton`, in the section and in the dialog.

### Moved actions (behaviour otherwise unchanged)

| Before | After |
| --- | --- |
| Save Instructions and Publish Instructions as the same plain button | Save Instructions secondary, in the Draft panel; Publish Instructions the page's one primary, in the Publish panel |
| Revert: an inline "Revert to v1?" group with a red button | A destructive `ConfirmDialog` "Revert to v1?" (confirm still "Yes, revert to v1") |
| Rollout: an inline `section role="dialog"` under the heading | A modal `Dialog`. It must be closed (Not now, Escape or Done) before going back to the page. |
| Bulk-revert offer: an inline `section role="dialog"` | A modal `Dialog` |
| "Unpublished Draft changes (not included)" pill | **Draft** badge plus "changes not included" |
| Results: one line per Agent | A count of succeeded, skipped and failed, then one line per Agent. The Agents list's bulk revert shares `BulkResults`, so it shows the count too. |
| "N Agents behind the Current Version (v2)." and "(behind)" text | The count with a version chip; version chips, Not live and **Instructions behind** badges in the table |
| Versions as a bordered list with a "Current" pill | A timeline of version chips with the **Current** badge |
| Compare: a server-computed diff (`GET …/instructions/diff`), shown as a list | `Diff` from the two texts the page already has (the Versions and the saved Draft). The Studio no longer calls the diff endpoint, which stays in the API. |

Routes and permissions are unchanged. Apart from the diff call, the API calls are unchanged.

## Test seams

The spec's frontend seams:

- **Network seam:** `renderStudio` with MSW, at the Instructions URL.
  - `InstructionsTab.test.tsx` covers the character count, Save Instructions as secondary, Publish as the page's only primary, the four panel headings, and the error `EmptyState`.
  - `InstructionsVersions.test.tsx` covers the timeline: the order, a version chip on each Version, and the Current badge. It also covers the revert `ConfirmDialog` (its description, focus on Cancel, confirm, cancel returning focus, refusal), publishing and its refusals.
  - `InstructionsDrafts.test.tsx` covers Compare: `Diff` rows with both line numbers and marks, the summary, any two Versions, identical sides, the Draft never published, waiting for the Draft, the Draft failing to load, and the comparison following a saved Draft. It also covers stale saves.
  - `BulkRollout.test.tsx` covers the rollout `Dialog`: modal, its description, focus on the first Agent, pre-selection, version chips, the Draft and Not live badges, the counted results, and Escape closing it without publishing. It covers the bulk-revert `Dialog`, and the Agents-behind summary and table badges.

  Each changed test was written red first, against the old page, then made green.
- **Component seam:** `design/Badge.test.tsx` covers the `current` kind.
- **End-to-end seam:** `instructions-versions.spec.ts` and `bulk-rollout.spec.ts` are updated for the modal rollout dialog (closing it with Not now), the revert alertdialog, Compare's Diff and the badges. They were not run (no stack). They type-check and lint.

The seams were not confirmed with a human (none was available), so the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | The Instructions editor, character count, Draft actions and Publish (the one primary) follow the recipes | Test: "the editor counts characters, saving the Draft is secondary and Publish is the page's one primary action". Screenshots `instructions-*`. |
| 2 | Versions are a timeline with the Current Version badged; any two can be compared and the diff uses `Diff` | Tests: "the history is a timeline of every Version newest first, with the Current one badged", "an Editor compares any two Instructions Versions" and the Compare tests above. Screenshots `instructions-*` and `compare-v1-v2-*`. |
| 3 | The rollout offer is a `Dialog` with every eligible Agent pre-selected and Draft changes badged; results show succeeded, skipped and failed per Agent | Tests: "publishing Instructions opens the rollout dialog with the Agents that can take it pre-selected" and "the results say which Agents were skipped or failed, and why". Screenshots `rollout-dialog-*`, `rollout-results-*` and `bulk-revert-offer-*`. |
| 4 | The Agents-behind summary uses badges instead of plain text | Test: "the Instructions page shows how many Agents are behind and which Version each one pins". Screenshot `instructions-*` (Agents panel). |
| 5 | Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR | The table above is also in the PR. All Studio tests pass (counts below). |
| 6 | The palette ratchet baseline is lowered to the new count | The new count is **24**, the same as before. These files had no palette classes left after 11-03, and the new code uses tokens and recipes only. The baseline equals the count ([frontend-tests.log](frontend-tests.log)). |
| 7 | Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas | [screenshots/](screenshots/) has 7 views × `-light`, `-dark` (system) and `-chosen-dark`: the Instructions page, Compare of v1 and v2, an archived Project, the revert confirmation, the rollout dialog, its results, and the bulk-revert offer. They follow the design README's recipes, now with a Project Instructions entry. |
| 8 | axe reports zero AA violations on the changed pages in both Appearances | [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` and `wcag22aa`, on every view above × 3 Appearances, **0 violations**. |
| 9 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams are above. Coverage is in [frontend-tests.log](frontend-tests.log). |
| 10 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | **Current Version** names the timeline and its Current badge. **Behind** names the chips and the Instructions behind badge. There are no new terms. No ADR decision changed. |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `b51b3f9`, which contains `origin/candidate-reskin` (`0b65fe4`). Each log's first line names its command and commit. GitHub Actions is down, so these are local.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 74 files, **970 tests**, 100% statements (4356/4356), branches (3041/3041), functions (1566/1566) and lines (3832/3832). `embed.js` is 0.77 kB gzipped. 24 palette-class uses (baseline 24). | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` (Chrome) | exit 1: 12 passed, 2 failed. The failures were already on `origin/candidate-reskin` (see Gaps). | [e2e-harness.log](e2e-harness.log) |
| Screenshots and axe | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 21 screenshots (7 views × 3 Appearances), 0 axe violations. | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack.** There is no Docker daemon in this sandbox, so the backend, the two updated Playwright specs and `e2e/harness/axe.spec.ts` against the stack were not run. [shots.test.ts](shots.test.ts) stands in for the axe run: it serves the built Studio, answers the API with the unit tests' MSW fakes, and runs the same axe tags.
- **Navigation harness, failing before this ticket.** Two harness specs ("openSection follows a tab in a row not yet replaced by a switcher" and "sectionNames lists a tab row's tabs") still expect an "Organisation settings" tab row. 11-11 replaced that row with the Settings switcher and emptied `TAB_ROWS`. This branch doesn't touch `frontend/e2e/harness` or `frontend/e2e/fixtures`, so they fail the same way on `origin/candidate-reskin`. The harness is not part of the merge gate. It is left for whoever owns the helpers, to avoid colliding with the tickets running at the same time.
- **No pixel comparison.** The design canvas could not be opened from this sandbox. The comparison is against `docs/design/README.md`.
- **Concurrent tickets.** 11-06 also adds a `Badge` kind. This branch adds `current` near the top of the list so the two don't touch the same lines.
