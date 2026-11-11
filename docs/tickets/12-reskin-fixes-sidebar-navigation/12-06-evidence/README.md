# Evidence: ticket 12-06, Project Settings reskin and Embedding Model dialog

Branch `t/12-06`, from `origin/candidate-reskin` at `63a7569`. The claim commit `cedbfb1` set Status `in-progress`. Then:

- `0bdfa7e` is the reskin: `ProjectSettingsTab.tsx`, `EmbeddingModel.tsx`, the `Meter`'s `progress` option, their tests, and the `embedding-models` e2e spec.
- `4de8aa9` updates `docs/design/README.md` (*Project Settings*, the progress `Meter`) and the `studio-reskin` patterns.
- The last commit adds this folder and ticks the ticket.

No backend code, route, API call or permission changes. `frontend/packages/ui` is untouched.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

- **Header.** `PageHeader level={2}` "Settings" with "How this Project embeds, reads and screens its Documents. A change applies to every Agent in it." On an archived Project it says "This Project is archived, so its settings can't be changed."
- **Cards.** One `surface.panel` per setting, each a region named by its h3 title, with its explanation: Embedding Model, OCR, Flagged Chunks.
- **Embedding Model.** The active model in mono on a `sunken` row with **Change** (accessible name "Change Embedding Model"). Change opens the `Dialog` "Change the Embedding Model". The dialog has the model select, then a warning `Notice`: "Every Document in this Project is re-embedded with the new model in the background. The current model keeps serving until that finishes." A Project without Documents gets an info notice instead: "the new model is used at once". Then come **Cancel** and **Use this model**. A refusal shows in the dialog, which stays open. Cancel, Escape and ✕ close it and return focus to Change. A running Re-embed is a status line ("Re-embedding with voyage-3.5: N of M Chunks. Retrieval uses multilingual-e5-small until it finishes.") over a `Meter` named "Re-embedding progress" (`aria-valuetext` "N of M Chunks"). A failed Re-embed is an error `Notice` with its reason.
- **OCR.** A labelled checkbox row, "Read scanned PDFs with OCR". The hint is its accessible description, and the status line under it gives the current state.
- **Flagged Chunks.** The `fieldset role="radiogroup"` named by the card's title and described by its explanation. Each of the two choices is a bordered option with a title (the radio's name) and a one-line description (the radio's description). The chosen option takes `accent-soft`. The status line follows.
- **Saving.** As before, each setting shows the choice at once (optimistic), is disabled while it saves, and shows a refusal in its card.
- **Archived.** OCR and Flagged Chunks are shown disabled. The Embedding Model card, and with it Change, is left out.
- **Meter.** The new `progress` option keeps the fill `accent` all the way, because a Re-embed that is nearly done needs no warning colour.
- **Recipes.** `EmbeddingModel.tsx` no longer imports `BUTTON` / `INPUT` from `ProjectsPage`. It uses `button.*` and `field.*`, which is one of the importers 12-07 needs gone.

### Moved behaviour

| Before | After |
| --- | --- |
| "Change Embedding Model" button showed an inline form under the setting | "Change" (same accessible name) opens the "Change the Embedding Model" dialog with the same form ("Choose the Embedding Model") |
| Re-embed progress: native `<progress>` | `Meter` (role `meter`), "N of M Chunks" |
| Failed re-embed: red text | Error `Notice` (still `role="alert"`) |
| OCR: a fieldset (group "OCR") | A card (region "OCR"), checkbox described by its hint |

## Test seams

These are the spec's network seam (`renderStudio` with MSW) and the e2e spec. The tests were written red first: 15 failing, then green.

- `ProjectSettingsTab.test.tsx`:
  - new: "Settings opens with a header and a short description, then a card per setting…".
  - new: "an archived Project's Settings say why they can't be changed, show every setting disabled and offer no Embedding Model change".
  - OCR's hint as the checkbox's description, and the card's status.
  - the Flagged Chunk choices' descriptions.
  - The existing optimistic, disabled-while-saving and refusal tests still pass, unchanged.
- `EmbeddingModel.test.tsx`: the choice, re-embed and failure flows now go through the dialog. The re-embed test checks the dialog's warning and the meter's "1 of 3 Chunks". New tests:
  - the no-Documents notice;
  - the Cancel / Use this model buttons;
  - Cancel and Escape returning focus to Change;
  - the refusal staying in the open dialog;
  - the choices' loading and error states inside the dialog.
- `ProjectPage.test.tsx`: OCR is now a region, not a group.
- `Meter.test.tsx`: a progress meter stays accent.
- `e2e/tests/embedding-models.spec.ts` opens the dialog and checks both notices. Its axe call runs with the dialog open. `ocr.spec.ts` and `documents.spec.ts` need no change: the checkbox, radiogroup and radio names are kept.

The seams were not confirmed with a human (none was available), so the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | Section header and short description; Embedding Model, OCR and Flagged Chunk mode each a card with a title and explanation | `ProjectSettingsTab.tsx`. Test "Settings opens with a header…". Screenshots `project-settings-*`. |
| 2 | Current Embedding Model in mono with Change; Change opens a dialog with the model choice, a re-embed warning, then Cancel and Use this model | `EmbeddingModel.tsx`. Tests "changing the model of a Project with Documents…" (warning), "the dialog for a Project without Documents…" (buttons, Cancel, Escape, focus). Screenshots `dialog-embedding-model-*`, `dialog-embedding-model-no-documents-*`. |
| 3 | A running re-embed shows a meter with "N of M Chunks" and which model keeps serving; a failed one shows an error notice with its reason | Tests "changing the model…" (meter `aria-valuetext` "1 of 3 Chunks", "Retrieval uses multilingual-e5-small") and "a failed re-embed shows its error…". Screenshots `re-embed-running-*`, `re-embed-failed-*`. |
| 4 | OCR a labelled toggle row with hint and state; Flagged Chunk mode two described choices keeping radio-group semantics | Tests "the Settings tab shows OCR off by default…" (description, status) and "flagged Chunks are only marked by default…" (radiogroup, radio descriptions). |
| 5 | Each setting shows the choice at once, disabled while saving; error in its card | Existing tests "the box shows the setting asked for…", "the toggle is disabled while saving…", "the flagged Chunk setting shows the choice while it saves…" (the alert is inside the card). Screenshot `flagged-saving-*`. |
| 6 | Archived: settings shown disabled, no Embedding Model change | Test "an archived Project's Settings say why…", plus the two existing archived tests and `ProjectPage.test.tsx`. Screenshot `project-settings-archived-*`. |
| 7 | Design system only; palette ratchet passes | Only tokens and recipes are used: `surface`, `text`, `field`, `button`, `layout`, `Notice`, `Dialog`, `Meter`, `PageHeader`. The leftover `grep` on the touched files prints nothing. Ratchet: see [frontend-tests.log](frontend-tests.log). |
| 8 | Light and dark screenshots, wide (1440) and narrow (390), and the axe sweep in both Appearances | [screenshots/](screenshots/) has 42 images: 7 views × 2 widths × light / dark (system) / chosen-dark. [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`, **0 violations**, and no horizontal scroll at either width. |
| 9 | Tests at the highest seam; 100% line and branch coverage | Seams above. `make test-frontend`: see [frontend-tests.log](frontend-tests.log). |
| 10 | Glossary / ADRs | No new domain term: Embedding Model, Re-embed and Flagged Chunk mode already exist and are unchanged. No decision changed. `docs/design/README.md` gains *Project Settings* and the progress `Meter`. |

## Results

[run-checks.sh](run-checks.sh) ran these in the worktree. Each log's first line names its command and commit.

| Check | Command | Log |
| --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | [build.log](build.log) |
| Link check | `make link-check` | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` (Chrome) | [e2e-harness.log](e2e-harness.log) |
| Screenshots and axe | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

All seven ran at `4de8aa9` and exited 0:

- lint and `tsc` are clean;
- 79 files and **1039 tests** pass, with 100% statements (4562/4562), branches (3233/3233), functions (1644/1644) and lines (3991/3991);
- `embed.js` is 778 B gzipped;
- the palette ratchet reports **0 palette-class uses (none allowed)**;
- 2394 relative links resolve;
- 12 harness tests pass;
- 42 screenshots, with 0 axe violations and no horizontal scroll.

The first full run in this sandbox hit a timing flake in an unrelated test (`AgentPage.test.tsx`, "the Playground can't be reset while an answer streams in"). It ran under load from parallel worktrees. The test passes alone and in the logged run.

## Gaps

- **No compose stack.** There is no Docker daemon in this sandbox, so the updated `embedding-models` spec and the other stack specs were not run. They type-check and lint. [shots.test.ts](shots.test.ts) stands in for the axe run against the stack: it serves the built Studio and answers the API with the unit tests' MSW fakes. **Closed after spec 12 merged:** the whole compose-stack suite (`make e2e`'s steps, 118 tests) passed against a stack built from the integration branch, with the fixes it needed; see [12-e2e-evidence](../12-e2e-evidence/README.md).
- **Select chevron.** The dialog's select uses `field.select`. Its chevron is 12-01's, which is built in parallel.
- **Concurrent tickets.** 12-01, 12-02 and 12-08 are in flight on their own branches. 12-02 changes the New Project form that `embedding-models.spec.ts` also uses. Whichever lands second merges the other in.
