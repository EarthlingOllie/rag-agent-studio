# Evidence: ticket 11-06, Documents and Document viewer

Branch `ticket/11-06-documents-viewer`, from `origin/candidate-reskin` at `034a445` (the merge of 11-05, #86). The claim commit `35e9f0b` set Status `in-progress`. Then:

- `c349e20` changes two design-system parts, each with tests. A `Menu` inside `BulkBar` keeps its own keys: the bar ignores a key a control already handled. `Badge` gains `flagged` ("Flagged", `flag-soft`).
- `86684e7` is Documents and the Document viewer, with their unit tests. It lowers the palette baseline from 24 to 19.
- `4def692` updates the e2e specs that use Documents, with a new `e2e/fixtures/documents.ts` for the ⋯ menu, the Tags dialog and the bulk bar.
- `657d4d5` adds **Knowledge Base figures** to `GLOSSARY.md`, updates **Document viewer** and **Tag**, and updates `docs/design/README.md` and the `studio-reskin` patterns.
- `d2ade95` merges `origin/candidate-reskin` at `0b65fe4` (11-11 and 11-12). The only conflicts were the `Badge` kinds: Flagged, Working and Check failed are all kept.
- `14733a7` is this folder's scripts. The last commit changes only this folder and the ticket file.

No backend code, route, API call or permission changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

**Documents** (`projects/DocumentsTab.tsx`). The Project's `PageHeader` (from 11-05) sits above it. Then, top to bottom:

- **Knowledge Base figures**: four `StatCard`s in a region "Knowledge Base".
  - Documents against the quota ("3 / 500").
  - Chunks.
  - Flagged chunks, in `flag` when above zero.
  - The Embedding Model.

  They count the whole Project, whatever the filters show. They come from a second, unfiltered `useDocuments`. It shares the cache with the list when there is no filter.
- **Toolbar** (`role="search"`):
  - the search pill ("Search by name");
  - Tag chips, a `Segmented` "Filter by Tag" (All, then each Tag; hidden while there are none);
  - **Manage tags**;
  - then, on the right, Clear filters (while filtered), the status filter ("Status", Any status) and **Upload**, the one primary. Upload is a pill-shaped label around the file input.
- **Drop zone**: a quiet `surface.dropzone` that says what it takes. It turns `accent-soft` while a file is dragged over it.
- **Notices**: a full quota (warning), failed Documents ("1 Document failed to process. Retry it from its ⋯ menu, or upload a fixed copy.", warning), upload refusals (error, in the Uploads list) and a refused retry (error).
- **Bulk bar**: `BulkBar` ("2 Documents selected") with **Add Tag** and **Remove Tag** menus listing the Tags, and Clear selection.
- **Table** (`table.wrap`): Select, Name, Type, Tags, Status, Chunks, Flagged, Size and ⋯.
  - Type is PDF, DOCX, PPTX, HTML, Markdown or Text, else File.
  - Tags are `Tag` pills.
  - Status is a `Status` dot, with the failure category and message, and any new edition's progress, under it.
  - Flagged is `FlagCount`.
  - ⋯ ("More actions for <name>", menu "Actions for <name>") holds **Retry** and **New edition** (only once the Document and any new edition are Ready or Failed, as before), **Edit Tags** and **Delete** (danger).
  - An archived Project has no ⋯, no selection, no Upload and no drop zone, as before.
- **Dialogs**:
  - **Tags** (from Manage tags) holds the Tags panel: create, rename, delete with the scoped-Agents warning, as before.
  - **Tags for <name>** (from Edit Tags) has the checkboxes and Save Tags.
  - **Delete <name>?** is a destructive `ConfirmDialog`: "Its 12 chunks stop being retrieved at once." A refusal shows in the dialog.
- **Toasts** (a `ToastProvider` around the section, as 11-11 did for settings):
  - "Deleted <name>.", "Retrying <name>." and "Saved the Tags on <name>.";
  - "Added <Tag> to 2 Documents." and "Removed <Tag> from 2 Documents.".

  None offers Undo: none of these can be reversed through the API.
- **States**: `Skeleton` "Loading Documents"; `EmptyState` "No Documents yet", "No Documents match these filters" and the error "The Documents could not be loaded".

**Document viewer** (`projects/DocumentViewer.tsx`, `shell/StudioBreadcrumb.tsx`):

- **The Document crumb**: the breadcrumb ends `… / HR handbook ▾ / Documents ▾ / handbook.pdf`.
  - The Document's name is the current crumb. It reads "Document" until the Document loads, or if it can't be loaded.
  - The Documents switcher is no longer the current crumb there. It leads back to the list, so the "All Documents" link is gone.
- **Header**: the name, a "Document details" list (status dot and any error, type, size, chunks, flagged count) and Download original (`button.secondary`). When Chunks are flagged, a warning `Notice` says how many.
- **Body**: the converted markdown in a panel, beside the Chunks.
  - Each Chunk is a card with its number, heading path and pages.
  - A flagged Chunk's card is edged in `flag` and badged **Flagged**, above the flag's note and Clear flag.
  - Paging is `Pagination` "Chunk pages" (Previous page, page numbers, Next page).
- **States**: `Skeleton` "Loading the Document" and "Loading Chunks"; `EmptyState` (error) "This Document could not be loaded".

### Moved actions (behaviour otherwise unchanged)

| Before | After |
| --- | --- |
| "Choose files to upload" link in the drop zone | **Upload** primary in the toolbar (the drop zone still takes dropped files) |
| Quota sentence "N of M Documents in this Project's quota…" | Documents stat card "N / M"; a warning `Notice` when the quota is full |
| Retry, New edition, Delete buttons in each row | Row ⋯ menu: Retry, New edition, Edit Tags, Delete |
| "Edit Tags" under each row's Tags, an inline form | ⋯ → Edit Tags, the "Tags for <name>" `Dialog` |
| Inline "Delete <name>?" group in the row | ⋯ → Delete, the "Delete <name>?" `ConfirmDialog` (confirm "Delete <name>") |
| Tags panel always on the page | **Manage tags** in the toolbar opens it in the "Tags" `Dialog` |
| "Filter by Tag" select | Tag chips: `Segmented` "Filter by Tag" (All first) |
| Bulk tagging fieldset: Tag select, Apply to selected, Remove from selected | `BulkBar`: Add Tag ▾, Remove Tag ▾, Clear selection |
| (none) | Toasts after Delete, Retry, saving Tags and bulk Tag changes |
| (none) | Knowledge Base figures; a notice counting failed Documents |
| Document viewer "All Documents" link | The breadcrumb's Documents switcher; the Document's name is the last crumb |
| Viewer Chunk paging: Previous / Next | `Pagination` with page numbers |

The filters, uploads, editions, retries, Tags, deletion, polling, routes, API calls and permissions work as before.

## Test seams

The spec's frontend seams:

- **Network seam**: `renderStudio` with MSW.
  - The new `projects/DocumentsPage.test.tsx` (20 tests) covers:
    - the figures (whole Project while filtered; flag colour only above zero);
    - the columns, file type, Tag pills, status and flagged count;
    - each row's ⋯ items by state, and an archived Project;
    - Delete's `ConfirmDialog` and toast, Retry's toast, the Tags dialog and the Tag chips;
    - the bulk bar's menus, toasts and empty-Tags state, and Edit Tags' toast;
    - the failed and quota notices, the empty and loading states, Upload and the drop zone;
    - the deletion wording for 0 and 1 chunks.
  - `DocumentsTab.test.tsx` and `DocumentTags.test.tsx` were updated to reach moved actions through the ⋯ menu, the dialogs and the bulk bar. They now assert the dialog refusal, the disabled Retry while a retry runs, the `accent` drag state and the muted retry message.
  - `DocumentViewer.test.tsx` covers the Document crumb and going back through the switcher, the details, the cards and Flagged badges, `Pagination`, and the loading and error states.
  - `SignedInShell.test.tsx` covers a Document page still being under Documents, with its own crumb current.
  - `ProjectPage.test.tsx` was updated for the new empty text and the Toast live region.

  Each new test was written red first, against the old page. There were 14 failures in `DocumentsPage.test.tsx` and 5 in `DocumentViewer.test.tsx`.
- **Component seam**: `design/controls.test.tsx` (a `Menu` inside `BulkBar`, red first) and `design/Badge.test.tsx` (Flagged, red first).
- **End-to-end seam**: these specs are updated but were not run (no stack): `documents`, `document-editions`, `ingestion-failures`, `ocr`, `retention`, `tags` and `tag-scoping`, plus the new `e2e/fixtures/documents.ts`. The upload label in the other specs (`project-deletion`, `llm-classifier`, `embedding-models`, `agent-config`, `playground`) changed too.

The seams were not confirmed with a human (none was available), so the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | Stat cards show Documents against the quota, Chunks, flagged chunks (flag colour when above zero) and the Embedding Model | Tests: "stat cards show Documents against the quota, Chunks, flagged chunks in the flag colour, and the Embedding Model" and "no flagged chunks keeps the stat card's quiet colour". Screenshot `documents-*`. |
| 2 | Rows show the file type, `Tag`, `Status` and `FlagCount`; Retry, New edition, Edit Tags and Delete move into a ⋯ menu | Tests: "rows show the file type, Tag pills, a status dot and the flagged count" and "Retry, New edition, Edit Tags and Delete are in each row's ⋯ menu…". The `DocumentsTab.test.tsx` flows go through the menu. Screenshot `menu-row-actions-*`. |
| 3 | The Tags panel opens from Manage tags; bulk selection uses `BulkBar` | Tests: "Manage tags opens the Tags panel in a dialog" and "selecting Documents shows the bulk bar…". All of `DocumentTags.test.tsx`. Screenshots `dialog-manage-tags-*` and `bulk-bar-*`. |
| 4 | Upload, ingestion failures and limits use `Notice`, `Toast` and `ConfirmDialog` | Upload refusals and a refused retry are error `Notice`s. Failed Documents and a full quota are warning `Notice`s. Delete is a `ConfirmDialog`. Delete, Retry, Tags and bulk changes are toasts. Tests: "failed Documents and a full quota are explained in notices above the table", "Delete asks in a ConfirmDialog, then confirms with a toast" and the upload refusal tests. Screenshots `confirm-delete-document-*` and `toast-deleted-*`. |
| 5 | The Document viewer shows the document crumb, the markdown and paged chunks on cards, with flagged chunks badged | Tests: "the breadcrumb ends with the Document's name…", "the viewer shows the Document's type, size and Chunks, its Chunks on cards, and badges the flagged ones" and "the Chunk list of a large Document pages through the API". Screenshot `document-viewer-*` (60 Chunks, one flagged, paged). |
| 6 | Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR | The moved-actions table is above and in the PR. All 48 `DocumentsTab` tests and 16 `DocumentTags` tests still pass with the same API calls. |
| 7 | The palette ratchet baseline is lowered to the new count | 24 → **19** (`frontend/palette-baseline.json`). The old Documents page's `border-slate-700` and `text-slate-700` and others are gone ([frontend-tests.log](frontend-tests.log): "19 palette-class uses (baseline 19)"). |
| 8 | Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas | [screenshots/](screenshots/) has 12 views × `-light`, `-dark` (system) and `-chosen-dark`, 36 in all. The views are Documents (filled, empty, no match, a Tag chip chosen, archived), the ⋯ menu, both Tags dialogs, the bulk bar with Add Tag open, the Delete confirmation, the toast after it, and the Document viewer. The layout follows the design README's Documents drawing: figures, toolbar, quiet drop zone, then the table with ⋯. |
| 9 | axe reports zero AA violations on the changed pages in both Appearances | [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` and `wcag22aa`, on 12 views × 3 Appearances, **0 violations**. |
| 10 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams are above. Coverage is in [frontend-tests.log](frontend-tests.log): 100% statements (4374/4374), branches (3070/3070), functions (1577/1577) and lines (3844/3844). |
| 11 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | **Knowledge Base figures** added. **Document viewer** and **Tag** updated (Document crumb, cards, Manage tags, chips, ⋯ Edit Tags, bulk bar). No ADR decision changed. |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `14733a7`. That commit contains `origin/candidate-reskin` at `0b65fe4` (merged in `d2ade95`). Each log's first line names its command and commit. GitHub Actions is down, so these are local.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 75 files, **990 tests**, 100% coverage. `embed.js` is 0.77 kB gzipped. 19 palette-class uses (baseline 19). | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` (Chrome) | exit 1: 12 passed, 2 failed. Both failures predate this branch (see Gaps). | [e2e-harness.log](e2e-harness.log) |
| Screenshots and axe | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 36 screenshots, 0 axe violations. | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **Harness failures on `candidate-reskin`.** Two tests in `e2e/harness/navigation.spec.ts` fail: "openSection follows a tab in a row not yet replaced by a switcher" and "sectionNames lists a tab row's tabs".
  - They test the "Organisation settings" tab row. 11-11 (#88) turned that row into a switcher and emptied `TAB_ROWS`, so the base branch fails them too.
  - This ticket changes neither file. It leaves the fix to whoever owns the helpers, so it doesn't collide with 11-08 running alongside.
  - The harness is not part of the merge gate.
- **No compose stack.** There is no Docker daemon in this sandbox, so the backend, the updated Playwright specs and `e2e/harness/axe.spec.ts` against the stack were not run.
  - The specs type-check and lint.
  - [shots.test.ts](shots.test.ts) stands in for the axe run. It serves the built Studio, answers the API with the unit tests' MSW fakes and runs the same axe tags.
- **No pixel comparison.** The design canvas could not be opened from this sandbox. The comparison is against `docs/design/README.md` and the `studio-reskin` patterns.
- **Tag chips are a radio group** (`Segmented`), not the `aria-pressed` buttons the patterns sketched. Only one Tag filter applies at a time, as with the old select, so a single-choice group says that.
- **The Embedding Model card shows the model id**, as the Settings section does. It does not look up a display name.
