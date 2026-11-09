# Evidence: ticket 11-05, Project frame

Branch `ticket/11-05-project-frame`, from `origin/candidate-reskin` at `61c67f3` (the merge of 11-04, #85). The claim commit `aa8532a` set Status `in-progress`. Then:

- `1b39f5a` changes three design-system parts, each with tests. A `Menu` item's number hint is visual only (`aria-hidden`). `ConfirmDialog` takes a `body` and `confirmDisabled`. `EmptyState` takes `level={1}`, so it can be a whole page's heading.
- `61ffcba` updates the navigation helpers. They gain the "Projects" menu, and "Project sections" is no longer in `TAB_ROWS`. Item names leave out hidden hints. The Playwright harness spec follows.
- `21ecc5b` is the Project frame: the Project and section switchers, the page header and its ⋯ menu, the confirmations, the Embedding Model in Settings, and the states. It also updates the unit and end-to-end tests.
- `dedc51d` adds **Project section** to `GLOSSARY.md` and updates `docs/design/README.md` and the `studio-reskin` patterns.
- `becf773` is this folder's scripts. The last commit changes only this folder and the ticket file.

No backend code, route, API call or permission changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

**The breadcrumb inside a Project** (`shell/StudioBreadcrumb.tsx`, `ProjectBreadcrumb`) is computed from the route, as before:

| Where you are | Breadcrumb (current crumb in bold) |
| --- | --- |
| A Project section | `Analytical Engines / Projects ▾ / HR handbook ▾ / **Documents ▾**` |
| The Document viewer | `… / HR handbook ▾ / **Documents ▾**` (its own crumb is 11-06) |
| An Agent, a Conversation | `… / HR handbook ▾ / **Agents ▾**`, `**Conversations ▾**` (the Agent crumb is 11-08) |
| A Project loading or not found | `Analytical Engines / Projects ▾ / **Project ▾**` |

- **Project switcher**, "<Project>, Projects". It lists the Organisation's open Projects (`useProjects(…, false)`), each a router link to its Documents, with the open one current. **All Projects** comes last and links to the Projects list. Archived Projects are opened from the Projects list, as before.
- **Section switcher**, "<section>, Project sections". It lists Documents, Instructions, Agents, Conversations, Analytics and Settings, each with its icon and a number hint 1–6, as router links. Documents is matched exactly (it is the index route) and also holds the Document viewer. The other sections hold their inner pages.
- The hints are visual labels (`aria-hidden`), so an item's name is "Agents", not "Agents3". The spec makes binding the keys a later ticket.
- **The Organisation's section switcher stays** as an ancestor crumb inside a Project. Cost, Settings and Security were one click away from a Project in the side menu, and still are. This is the one place the build differs from the design README's table, which showed `Org ▾ / Project ▾ / Documents ▾`. The table now shows what was built, with the reason.

**The page header** (`projects/ProjectPage.tsx`) is `PageHeader`: the name, the description (when there is one), **Edit details** (not on an archived Project, as before) and a ⋯ button named "More Project actions", which opens the menu "Project actions":

| Project | ⋯ menu |
| --- | --- |
| Active, any role | Archive |
| Archived, Owner | Delete permanently (danger) |
| Archived, Editor | no ⋯ button: nothing to offer |

- **Archive** asks first in a destructive `ConfirmDialog`. It is an alertdialog, "Archive HR handbook?", with focus on Cancel, the same sentence as before plus "An Owner can restore it.", and the confirm button "Yes, archive HR handbook". A refusal shows the API's reason under the header, as before.
- **Delete permanently** is a destructive `ConfirmDialog`, "Delete Old launch permanently", with the same warning. The name field ("Type Old launch to confirm") is in the dialog's `body`, inside a form, so Enter confirms. It takes focus. The confirm button stays disabled until the name is typed exactly, and a refusal shows in the dialog. Success opens the Projects list with "Old launch is being deleted permanently.", as before.
- **Restore** stays in the archived notice (Owners only), as before.

**States.** Loading is `<Skeleton label="Loading the Project" />`. Not found is `<EmptyState level={1} icon="projects" title="Project not found" …>`, still the page's h1. A failed load is `<EmptyState tone="error" title="The Project could not be loaded" description="Try again shortly.">` (role alert).

**Embedding Model** moved from under the Project header (shown on every section) into the **Settings** section, above OCR and Flagged Chunks. As before, it is not shown for an archived Project.

### Moved actions (behaviour otherwise unchanged)

| Before | After |
| --- | --- |
| Project tab row (`navigation "Project"`): Documents, Instructions, Agents, Conversations, Analytics, Settings | Section switcher "<section>, Project sections", with icons and number hints |
| "All Projects" link above the Project | Project switcher → All Projects |
| (none) | Project switcher: jump straight to another open Project |
| "Archive" button under the header, then an inline "Yes, archive …" panel | ⋯ → Archive, then the "Archive …?" `ConfirmDialog` (confirm button still "Yes, archive …") |
| "Delete permanently" button in the archived notice, then an inline form "Delete … permanently" | ⋯ → Delete permanently, then the "Delete … permanently" `ConfirmDialog` with the name field |
| Embedding Model setting under the header on every section | Settings section |
| "Loading the Project…" text; "The Project could not be loaded. Try again shortly." text | `Skeleton` "Loading the Project"; error `EmptyState` |

Routes, API calls, permissions, the Projects list and every section's own content are unchanged.

## Test seams

The spec's frontend seams:

- **Network seam:** `renderStudio` with MSW, at the Project's URL.
  - `shell/SignedInShell.test.tsx` covers the breadcrumb inside a Project and the Project switcher (open Projects as links, the current one, All Projects, switching). It covers the section switcher (order, `href`s, icons, hidden hints, current item) and inner pages keeping their section. It also covers an archived Project, and a Project that can't be loaded.
  - `projects/ProjectPage.test.tsx` covers:
    - no tab row and no All Projects link;
    - the ⋯ menu's items by state and role;
    - Archive's dialog, cancel, confirm, refusal and the error clearing;
    - Restore;
    - deletion's dialog, its typed name, Enter, cancel and refusal;
    - the Embedding Model only in Settings, and not for an archived Project;
    - the not-found, loading and error states.
  - `EmbeddingModel.test.tsx` now opens the Settings section.

  Each new test was written red first, against the old frame, then made green. There were 7 failures in the shell file and 8 in the Project page file.
- **Component seam:** `design/Dialog.test.tsx` covers `body` and `confirmDisabled`. `design/states.test.tsx` covers `EmptyState`'s `level`.
- **End-to-end seam:** the Playwright helper's harness spec now covers an item with a hidden number hint, and the remaining tab row ("Organisation settings"), in Chrome. These specs are updated but were not run (no stack): `projects`, `documents`, `instructions`, `project-deletion` and `embedding-models`. They use the Project switcher, the ⋯ menu, the alertdialog and the Settings section.

The seams were not confirmed with a human (none was available), so the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | The Project crumb lists the Projects plus All Projects; the section crumb lists Documents, Instructions, Agents, Conversations, Analytics and Settings with icons and number hints | Tests: "the Project switcher lists the open Projects as links, plus All Projects" and "the section switcher lists the Project's sections with icons and number hints, as links". Screenshots `menu-projects-*` and `menu-project-sections-*`. |
| 2 | The Project tab row and the All Projects link are gone | Test: "the Project frame has no tab row and no All Projects link: the breadcrumb does both". `TAB_ROWS` no longer lists "Project sections" in either helper. |
| 3 | `PageHeader` shows the name and description with Edit details and a ⋯ menu holding Archive and permanent deletion; confirmations use `ConfirmDialog` | `ProjectHeader` in `ProjectPage.tsx`. The tests for the ⋯ menu, Archive and deletion are listed above. Screenshots `menu-project-actions-*`, `confirm-archive-*` and `confirm-delete-*`. |
| 4 | The Embedding Model setting moves into the Project's Settings section | `ProjectSettingsTab.tsx`. Tests: "the Embedding Model is set in the Project's Settings section, not on every page" and the 8 `EmbeddingModel.test.tsx` tests, now on `/settings`. Screenshot `project-settings-*`. |
| 5 | Not-found and loading states use `EmptyState` and `Skeleton` | Tests: "an unknown Project is not found" and "a Project page shows its loading and error states". Screenshot `project-not-found-*`. |
| 6 | Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR | The moved-actions table is above and in the PR. No routes, API calls or permissions changed. All Studio tests pass (counts below). |
| 7 | The palette ratchet baseline is lowered to the new count | The new count is **24**, the same as before. The Project frame had no palette classes left after 11-03, and the new code uses tokens and recipes only. The baseline equals the count ([frontend-tests.log](frontend-tests.log)). |
| 8 | Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas | [screenshots/](screenshots/) has every page inside a Project (Documents, Document viewer, Instructions, Agents, Agent, Conversations, Conversation, Analytics, Settings), an archived and a missing Project, the two switchers and the ⋯ menu open, and both confirmations. Each is `-light`, `-dark` (system) and `-chosen-dark`. The frame follows the README's layout: `PageHeader` with `[Edit details] [⋯]` on the right, and the switcher crumbs in the top bar. |
| 9 | axe reports zero AA violations on the changed pages in both Appearances | [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` and `wcag22aa`, on every view above × 3 Appearances, **0 violations**. |
| 10 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams are above. Coverage is in [frontend-tests.log](frontend-tests.log). |
| 11 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | **Project section** added, and **Breadcrumb** names the Project switcher. No ADR decision changed: ADR-0013 already says navigation is the breadcrumb. |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `becf773`, which is `origin/candidate-reskin` (`61c67f3`) plus this branch. Each log's first line names its command and commit. GitHub Actions is down, so these are local.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 74 files, **950 tests**, 100% statements (4347/4347), branches (3012/3012), functions (1556/1556) and lines (3824/3824). `embed.js` is 0.77 kB gzipped. 24 palette-class uses (baseline 24). | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` (Chrome) | exit 0, 14 passed | [e2e-harness.log](e2e-harness.log) |
| Screenshots and axe | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 48 screenshots (16 views × 3 Appearances), 0 axe violations. | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack.** There is no Docker daemon in this sandbox, so the backend, the five updated Playwright specs and `e2e/harness/axe.spec.ts` against the stack were not run. The specs type-check and lint, and the helper they call is checked by the harness spec in Chrome. [shots.test.ts](shots.test.ts) stands in for the axe run: it serves the built Studio, answers the API with the unit tests' MSW fakes, and runs the same axe tags.
- **Deeper crumbs** (a Document's name, the Agent switcher) are 11-06 and 11-08. Until then, the section switcher is the current crumb on those pages.
- **No pixel comparison.** The design canvas could not be opened from this sandbox. The comparison is against `docs/design/README.md` and the patterns.
- **Concurrent tickets.** 11-11 removes the "Organisation settings" tab row from the same helpers' `TAB_ROWS` and harness spec. Whichever lands second resolves the small conflict there.
