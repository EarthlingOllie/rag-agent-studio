# Evidence: ticket 12-02, Project details dialog (New Project and Edit details)

Branch `t/12-02`, from `origin/candidate-reskin` at `63a7569`. The claim commit `ceb8b6b` set Status `in-progress`; `93a8705a` builds the dialog; the last commit adds this folder, ticks the criteria and sets Status `done`.

No backend code, API call, route or permission changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

- **`projects/ProjectDetailsDialog.tsx`** (new): one `ProjectDetailsDialog` with `mode: "create" | "edit"`, the design system's `Dialog` without the corner ✕, a form named "New Project" or "Project details", `FormError`, `ProjectFields` (Name, required, on `field.input`; Description on `field.textarea`; labels on `field.label`), and a footer with Cancel (`button.secondary`) and the primary action (`button.primary`: "Create Project" / "Save", "Creating…" / "Saving…" while pending). `NewProjectDialog` creates the Project and opens it; `EditProjectDialog` saves, closes, and shows the toast "Project details saved".
- **Projects page**: the inline `NewProjectForm` is removed; a **New Project** button (`button.primary`) sits where the form was (under the active list; not shown while archived Projects are shown) until 12-03 places it in the header. `ProjectFields` and `projectDetails` moved out of `ProjectsPage.tsx` into the dialog's module; the `BUTTON` / `INPUT` exports stay for their other importers (12-03, 12-07).
- **Project header**: Edit details opens the dialog and stays in the header while it is open; nothing renders inline under the header. The header is wrapped in a `ToastProvider` for the confirmation.
- **Tests** that found a status anywhere on a Project page (`InstructionsTab.test.tsx`, `InstructionsVersions.test.tsx`) now find it by its words, since the Project page hosts the toast's live region.
- **e2e specs** that create a Project click **New Project** before filling the form (23 places in 20 specs); `projects.spec.ts`'s rename already fills the "Project details" form, now inside the dialog.

### Moved actions

| Before | After |
| --- | --- |
| New Project was an inline form under the Projects list | A New Project button there opens the New Project dialog |
| Edit details replaced itself with an inline form under the Project header | Edit details stays put and opens the Project details dialog |

## Test seams

The spec's network seam (`renderStudio` with MSW); the seams were not confirmed with a human (none was available), so the spec's own were used. Written red first (7 failing, then green):

- `ProjectsPage.test.tsx`: "an Editor creates a Project in the New Project dialog and lands on its page" (no inline form; Name required, empty, focused); "Cancel and Escape close the New Project dialog without creating anything, and focus returns to New Project"; "New Project is not offered while archived Projects are shown"; "a refused new Project says what to fix inside the dialog and keeps what was typed; other failures say to try again".
- `ProjectPage.test.tsx`: "an Editor renames a Project and edits its description in a dialog, and a toast confirms it" (current values, Edit details still present, the form not inside `main`, header updated, toast); "Cancel and Escape close the details dialog without saving, and focus returns to Edit details"; "a refused save says why inside the dialog and keeps what was typed".

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | Edit details opens a "Project details" dialog with the current name and description; Save closes it, the header shows the new values and a toast confirms | `ProjectPage.test.tsx` rename test; screenshots `project-details-dialog-*`, `project-details-saved-*` |
| 2 | The Edit details button stays in the Project header while the dialog is open; nothing renders inline under the header | Same test (button present, form not in `main`); `project-details-dialog-*` screenshots |
| 3 | New Project opens the same dialog in create mode (Name required, Description); Create Project opens the new Project | `ProjectsPage.test.tsx` create test; `new-project-dialog-*` |
| 4 | A refusal shows inside the dialog and keeps what was typed | Both "refused" tests; `new-project-refused-*` |
| 5 | Cancel and Escape close the dialog without saving, and focus returns to the button that opened it | Both Cancel/Escape tests (no request sent); [shots-axe.log](shots-axe.log) keyboard lines in a real browser, all four runs |
| 6 | The dialog's fields use the design system's field recipes | `ProjectDetailsDialog.tsx`: `field.label`, `field.input`, `field.textarea` |
| 7 | Until 12-03 places it in the header, New Project is a button where the inline form was; the inline New Project form is removed | `ProjectsPage.tsx`; create test asserts no "New Project" form before the click; `projects-*` screenshots |
| 8 | Design system only; the palette ratchet passes | Tokens and recipes only; [frontend-tests.log](frontend-tests.log) ends "0 palette-class uses under apps/studio/src (none allowed)." |
| 9 | Evidence: light and dark screenshots, wide (1440) and narrow (390), and the axe sweep in both Appearances | [screenshots/](screenshots/): 6 views × light, dark, narrow-light, narrow-dark (24 files); [shots-axe.log](shots-axe.log): **0 axe violations**, 0 overflows, 0 focus problems |
| 10 | Tests at the highest seam; 100% line and branch coverage | Seams above; [frontend-tests.log](frontend-tests.log): 1038 tests, 100% statements (4565/4565), branches (3227/3227), functions (1647/1647), lines (3994/3994) |
| 11 | New domain terms in `GLOSSARY.md`; ADRs updated if a decision changed | **Project details dialog** added under Knowledge; `docs/design/README.md` *Pages* describes it. No ADR decision changed (ADR-0013's `Dialog` and toast patterns are used as they are). |

## Results

[run-checks.sh](run-checks.sh) ran these at `93a8705a`. Each log's first line names its command and commit.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0; 79 files, 1038 tests, 100% coverage; 0 palette-class uses | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Changed e2e specs parse | `playwright test --project=studio --list` (projects, documents) | exit 0 | [e2e-list.log](e2e-list.log) |
| Screenshots, axe, overflow, focus | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome, API answered by the unit tests' MSW fakes) | exit 0; 24 views, 0 violations | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack.** The backend and the Playwright `studio` suite (including the 20 specs updated to open the dialog) were not run; they lint, type-check and list. `shots.test.ts` stands in for the axe sweep on the pages this ticket touches. **Closed after spec 12 merged:** the whole compose-stack suite (`make e2e`'s steps, 118 tests) passed against a stack built from the integration branch, with the fixes it needed; see [SCRATCH/spec12-e2e.md](../../../../SCRATCH/spec12-e2e.md).
- **No pixel comparison** with the design canvas (not reachable from the sandbox); the layout follows `docs/design/README.md` and the `NewAgentDialog` pattern.
