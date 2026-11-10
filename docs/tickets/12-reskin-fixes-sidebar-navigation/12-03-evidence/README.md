# Evidence: ticket 12-03, Projects list reskin

Branch `t/12-03`, from `claude/gallant-euler-zxqfxb` at `d302125` (which holds 12-01, 12-02, 12-04, 12-05, 12-06 and 12-08). The claim commit `de55744` set Status `in-progress`. Then:

- `1f3501d` is the reskin: `projects/ProjectsPage.tsx`, its tests and `ProjectPage.test.tsx` (the deletion test's filter), the `projects` and `project-deletion` e2e specs (the radio filter and the designed empty states), `docs/design/README.md` (*Projects list*) and the `studio-reskin` patterns (a one-line cell).
- `be70569` holds this folder's scripts.
- The last commit changes only this folder and the ticket file.

No backend code, route, API call, query shape or permission changes. `ProjectsPage.tsx` no longer uses its `BUTTON` / `INPUT` strings but still exports them: removing them is 12-07.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

- **Header.** `PageHeader` "Projects" (the page's one h1) with "Each Project holds the Documents its Agents answer from." and New Project (`button.primary`, opens the 12-02 dialog) on the right. New Project is hidden while Archived is shown.
- **Toolbar.** A `Segmented` radio group "Projects shown" (Active / Archived), as on Agents. It replaces the "Show archived Projects" / "Show active Projects" button.
- **Active Projects.** A `table.wrap` card named "Projects": Name (`table.link`, no underline), Description (`table.tdMuted`, cut to one line with an ellipsis; the full text is the cell's `title`), Documents and Agents (`table.thNumeric` / `table.tdNumeric`: right-aligned, mono).
- **Archived Projects.** A line saying archived Projects are hidden and don't serve, then "Restore one to bring it back." (Owners) or "Only Owners can restore them." (Editors). A `table.wrap` card named "Archived Projects": Name, the archived date in mono, and for Owners a `button.secondary` "Restore" in the row (named "Restore <Project>"). A restore is confirmed by a toast, "<Project> was restored.", and the Project leaves the list. A failed restore is the existing alert, "Something went wrong. Try again.".
- **States.** Loading: `Skeleton` "Loading Projects" / "Loading archived Projects". A failed load: an error `EmptyState` ("The Projects could not be loaded" / "The archived Projects could not be loaded", "Try again shortly."). No Projects: `EmptyState` "No Projects yet", "Create one with New Project to start collecting knowledge for a purpose.". No archived Projects: `EmptyState` "No archived Projects", "A Project you archive is kept here, with its Documents and Agents.".
- **Deleted.** "<Project> is being deleted permanently." after a deletion is a `Notice tone="success"` (still `role="status"`).

### Moved behaviour

| Before | After |
| --- | --- |
| "Show archived Projects" / "Show active Projects" button | `Segmented` radio group "Projects shown" (radios Active / Archived) |
| New Project button under the table | New Project in the page header, top right (hidden on Archived) |
| "Loading Projects…" / "Loading archived Projects…" text | `Skeleton`, status "Loading Projects" / "Loading archived Projects" |
| Load errors: plain `role="alert"` text | error `EmptyState` (still `role="alert"`) |
| "No Projects yet. …" / "No archived Projects." text | `EmptyState` headings "No Projects yet" / "No archived Projects" with a description |
| "<Project> was restored." inline status text | toast with the same words |
| "… is being deleted permanently." accent text | success `Notice` with the same words |

## Test seams

The spec's network seam (`renderStudio` with MSW) and the e2e specs. The tests were changed first (9 of 27 in the two files failing), then made green.

- `projects/ProjectsPage.test.tsx`:
  - the h1, its description, New Project, the "Projects shown" radio group (Active checked), no "Show archived Projects" button, the column headers and the rows;
  - the "No Projects yet" empty state; loading (status "Loading Projects") and the error state's heading;
  - New Project hidden after choosing Archived;
  - archived: the Owner's line, the columns and row, Restore, the toast's words in the polite live region, the "No archived Projects" empty state, and back on Active the restored Project;
  - the Editor's line ("… Only Owners can restore them.") and no row buttons; a failed restore's alert; the archived list's loading and error states.
- `projects/ProjectPage.test.tsx`: after a deletion the notice is a status and Archived shows the "No archived Projects" empty state.
- `e2e/tests/projects.spec.ts` and `e2e/tests/project-deletion.spec.ts` use the "Projects shown" radios and the empty states' headings.

The seams were not confirmed with a human (none was available), so the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | Page header titled Projects, a one-line description, New Project as its one primary action, top right | `PageHeader` in `ProjectsPage.tsx`. Test "Members see the active Projects…" checks the h1, the sentence and the button. Screenshots `projects-active-*`. |
| 2 | Segmented "Projects shown" (Active / Archived) replaces Show archived Projects; New Project hidden on Archived | `Segmented` with `SHOWN_OPTIONS`. Tests "Members see the active Projects…" (radios, no old button) and "New Project is not offered while archived Projects are shown". Screenshots `projects-archived-*` (no New Project). |
| 3 | Active Projects in a table card: Name a link without underline, Description on one line, counts right-aligned in mono | `table.wrap`, `table.link`, a `truncate` span in `table.tdMuted`, `table.thNumeric` / `table.tdNumeric`. Test checks columns, cells and links. Screenshots `projects-active-*` (a long description ends in an ellipsis). |
| 4 | Archived Projects in a table card with the archived date; Owners restore from the row and a toast confirms; Editors told only Owners can restore | Tests "archived Projects are listed apart, and Owners restore them…", "Editors see archived Projects but can't restore them". Screenshots `projects-archived-*`, `projects-restored-*` (the toast), `projects-archived-editor-*`. |
| 5 | Loading placeholder; error state; designed empty states for no Projects and no archived Projects | `Skeleton`, `EmptyState tone="error"`, `EmptyState`. Tests "the Projects list shows its loading and error states", "the archived list shows its loading and error states", "an Organisation without Projects says so", and the restore test's empty state. Screenshots `projects-loading-*`, `projects-error-*`, `projects-none-*`, `projects-restored-*`. |
| 6 | "Is being deleted permanently" message is a success notice | `Notice tone="success"`. `ProjectPage.test.tsx` deletion test; `project-deletion.spec.ts`. Screenshots `projects-deleted-*`. |
| 7 | Design system only, no palette classes or `dark:`; the palette ratchet passes | Only `../design` recipes and components; the local classes are layout utilities (`block max-w-md truncate`, `whitespace-nowrap`, `font-mono text-[13px]`, `text-sm text-muted`). [frontend-tests.log](frontend-tests.log): "0 palette-class uses under apps/studio/src (none allowed)." |
| 8 | Light and dark screenshots, wide (1440) and narrow (390), and the axe sweep in both Appearances | [screenshots/](screenshots/): 8 views (active, archived, archived as an Editor, restored with the toast, no Projects, loading, error, deleted notice) × wide and narrow × light, dark (system) and chosen dark = 48 images. [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`, **0 violations**, no horizontal scroll. |
| 9 | Tests at the highest seam; 100% line and branch coverage holds | Seams above. [frontend-tests.log](frontend-tests.log): `make test-frontend`, 81 files, 1072 tests, 100% statements (4614/4614), branches (3261/3261), functions (1671/1671) and lines (4038/4038). |
| 10 | New domain terms in `GLOSSARY.md`; ADRs updated if a decision changed | No new domain term (Project, Archive, Restore, Owner, Editor and Project details dialog are already defined). No decision changed; the design README's *Pages* gains the Projects list layout. |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `be70569`. Each log's first line names its command and commit. GitHub Actions is not used, so these are local.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0, 1072 tests, 100% coverage, `embed.js` 0.77 kB gzipped, 0 palette-class uses | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` (Chrome) | exit 0, 14 passed | [e2e-harness.log](e2e-harness.log) |
| Screenshots and axe | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 48 screenshots, 0 axe violations, no horizontal scroll. | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack.** The Docker daemon is not running in this sandbox, so the backend, the `projects` and `project-deletion` Playwright specs and `e2e/harness/axe.spec.ts` against the stack were not run. The specs type-check and lint. [shots.test.ts](shots.test.ts) stands in for the axe run: it serves the built Studio, answers the API with the unit tests' MSW fakes, and runs the same axe tags. No backend code changed.
- **No pixel comparison** with the design canvas; the comparison is against `docs/design/README.md` and the Agents list.
- **Concurrent tickets.** 12-07 removes the `BUTTON` / `INPUT` exports this file still carries. 12-09 and 12-10 change the shell and Agent pages, not this page.
