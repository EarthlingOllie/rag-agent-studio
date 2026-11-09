# Evidence: ticket 11-09, Agents list and bulk actions

Branch `ticket/11-09-agents-list-bulk`, from `origin/candidate-reskin` at `2362781` (the merge of 11-12, #87). The claim commit `5a8214b` set Status `in-progress`. Then:

- `d106ecf` gives `PageHeader` a `level={2}`, with a test, so a Project section can have a page header under the Project's own (which keeps the page's one h1).
- `e78953d` is the Agents section: the table card, the Live state badges, the bulk bar and its Revert confirmation, New Agent in the page header, and the Archived filter. It rewrites `AgentsTab.test.tsx` and updates `AgentArchive.test.tsx` and `AgentPublish.test.tsx`.
- `e4a3cf2` updates the twelve end-to-end specs that create an Agent or read the Agents list.
- `7356df2` adds **Live state** to `GLOSSARY.md`, updates **Bulk revert**, and describes a Project section's header and the Agents list in `docs/design/README.md`.
- `c36bb1e` is this folder's scripts. The last commit changes only this folder and the ticket file.

No backend code, route, API call or permission changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

**Page header.** The Agents section opens with `PageHeader level={2}`: "Agents", "Each Agent answers from this Project's Documents.", and **New Agent** (`button.primary`, the view's one primary) on the right. It is not offered on an archived Project, as the create form wasn't before. New Agent opens a `Dialog` "New Agent" holding the form (still a `form` named "New Agent"): Name takes focus, Enter or **Create Agent** creates it and opens the Agent's page, Cancel or Escape closes it and focus returns to New Agent. A refusal shows in the dialog.

**Toolbar.** A `Segmented` radio group "Agents shown": **Active** (the default) and **Archived**. Archived shows the archived Agents with the same explanation as before ("Only Owners can restore or delete them" or "Open one to restore it or delete it permanently").

**The table card** (`table.wrap`, named "Agents" or "Archived Agents"):

| Column | Shows |
| --- | --- |
| (checkbox) | "Select all Agents" in the header (indeterminate when some are), "Select <Agent>" per row. Only active Agents of an active Project. |
| Name | A link to the Agent's page (`table.link`) |
| Live | `Badge kind="live"` + the version chip (`Badge kind="version"`, read "Version 3"): **Live v3**; or `Badge kind="notLive"`: **Not live** |
| Draft | `Badge kind="draft"` (**Draft**, hover "Unpublished changes: the Draft differs from the Live Version.") when the Draft has unpublished changes, else — |
| Alerts | `Badge kind="budgetSpent"` (**Budget spent**) and `Badge kind="blocked"` (**Blocked by guardrail**), each with the same explanation as before on hover, else — |
| Draft saved / Archived | The date the Draft was last saved, or, for archived Agents, the date archived (as before) |

**Bulk bar.** Selecting Agents shows `BulkBar` above the table: "2 Agents selected", **Revert**, **Clear selection** (Escape clears too; the arrow keys move between its buttons). Revert asks in a destructive `ConfirmDialog` "Revert 2 Agents?" with the same sentence as before and "Yes, revert 2 Agents". The results are reported **per Agent** in a card above the table ("HR helper — Done: Reverted to v2 …", "Benefits FAQ — Skipped: …"), and the selection clears. A refusal of the whole request closes the dialog, shows the reason as an alert and keeps the selection; pressing Revert again clears it.

**States.** Loading is `Skeleton` "Loading Agents". A failed load is `EmptyState tone="error"` "The Agents could not be loaded" / "Try again shortly.". No Agents is `EmptyState` "No Agents yet" / "Create one with New Agent to answer questions from this Project's Documents."; no archived Agents is `EmptyState` "No archived Agents". "<Agent> was deleted permanently." is a success `Notice`.

### Moved actions (behaviour otherwise unchanged)

| Before | After |
| --- | --- |
| "New Agent" form under the list (Name, Create Agent) | Page header → **New Agent** → `Dialog` with the same form |
| "Show archived Agents" / "Show active Agents" button, heading switching to "Archived Agents" | `Segmented` "Agents shown": Active / Archived; the table's name switches |
| A list (`list "Agents"`) of rows | A table card (`table "Agents"`), one row per Agent |
| "Revert selected (N)" button (disabled at 0) in a "Bulk actions" group, then an inline "Revert N Agents? … Yes, revert …" panel | `BulkBar` "Bulk actions" (shown while Agents are selected) → **Revert** → `ConfirmDialog` "Revert N Agents?" (confirm still "Yes, revert N Agents") |
| (none) | "Select all Agents" in the header; Clear selection / Escape |
| "Live v3" and "Not live" pills, "Unpublished changes" pill | `Badge`s: Live + v3, Not live, Draft (hover: "Unpublished changes: …") |
| "Budget exhausted" and "Block rate spike" pills | `Badge`s **Budget spent** and **Blocked by guardrail**, the design system's words; the hover text keeps the reason, starting "Block rate spike:" for the second. The Agent page still says "Budget exhausted" and "Block rate spike" (11-08 owns it). |
| "Archived 2026-11-06" beside an archived Agent | Archived column |
| (none) | Draft saved column (the Agent's `draft_updated_at`, already in the API response) |
| Loading, error and empty text | `Skeleton`, error `EmptyState`, `EmptyState` |

Routes, API calls (list, create, bulk revert), permissions and the Agent page are unchanged.

## Test seams

The spec's frontend seams:

- **Network seam:** `renderStudio` with MSW, at the Agents section's URL. `projects/AgentsTab.test.tsx` covers the table (columns, rows, badges, links, hover text), New Agent (primary in the header, the dialog, Cancel and focus return, Enter, landing on the Agent page, a refusal), both empty states, an archived Project (no New Agent, no checkboxes), loading and error, the Archived filter, the bulk bar (count, Revert, the confirmation, Cancel, per-Agent results, cleared selection), Select all (indeterminate, all, none), Clear selection and Escape, a whole-request refusal, and both alert badges. Each test was written red first against the old list: all 12 failed, then passed. `AgentArchive.test.tsx` and `AgentPublish.test.tsx` now read the table and the filter.
- **Component seam:** `design/content.test.tsx` covers `PageHeader level={2}` (red first).
- **End-to-end seam:** twelve specs updated, not run (no stack): `agent-archive`, `agent-drafts`, `agent-publish`, `agent-revert`, `bulk-rollout`, `demo-pages`, `embed`, `five-minute-demo`, `operational-settings`, `playground`, `rate-limits` and `token-budget`. They click New Agent before filling the form, read `table "Agents"` rows, use the Archived radio and the bulk bar's Revert, and expect "Budget spent" in the list.

The seams were not confirmed with a human (none was available), so the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | Agents are listed in a table card with `Badge` for Live v<N>, Draft changes and Not live | Test "the Agents section is a table card …". Screenshots `agents-*`. |
| 2 | Selecting Agents shows `BulkBar` with Revert; results are reported per Agent | Tests "selecting Agents shows the bulk bar; Revert asks first, then reports each Agent's result", "Select all …", "a bulk revert refused as a whole …". Screenshots `bulk-bar-*`, `confirm-revert-*`, `revert-results-*`. |
| 3 | New Agent opens from a primary button in the page header; archived Agents are behind a filter | Tests "New Agent opens from the primary button in the page header …", "archived Agents are behind the Archived filter …". Screenshots `new-agent-*`, `agents-archived-*`. |
| 4 | The empty state uses `EmptyState` | Test "the empty states use EmptyState, pointing to New Agent". Screenshot `agents-empty-*`. |
| 5 | Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR | The moved-actions table is above and in the PR. No routes, API calls or permissions changed. All Studio tests pass (counts below). |
| 6 | The palette ratchet baseline is lowered to the new count | The count is **24**, the same as before: the Agents list had no palette classes left after 11-03, and the new code uses tokens, recipes and `Badge` only. The baseline equals the count ([frontend-tests.log](frontend-tests.log)). |
| 7 | Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas | [screenshots/](screenshots/): the list, the Archived filter, the empty list, the New Agent dialog, the bulk bar, the Revert confirmation and the results, each `-light`, `-dark` (system) and `-chosen-dark`. The layout follows the README's list-page pattern: `PageHeader` with the primary on the right, a toolbar, the bulk bar above a `table.wrap` card. |
| 8 | axe reports zero AA violations on the changed pages in both Appearances | [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` and `wcag22aa`, on 7 views × 3 Appearances, **0 violations**. |
| 9 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams are above. Coverage is in [frontend-tests.log](frontend-tests.log). |
| 10 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | **Live state** added; **Bulk revert** says it starts from the bulk bar. No ADR decision changed. |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `c36bb1e`, which is `origin/candidate-reskin` (`2362781`) plus this branch. Each log's first line names its command and commit. GitHub Actions is down, so these are local.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 74 files, **968 tests**, 100% statements (4368/4368), branches (3055/3055), functions (1570/1570) and lines (3840/3840). `embed.js` is 0.77 kB gzipped. 24 palette-class uses (baseline 24). | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` (Chrome) | exit 1: 12 passed, 2 failed. Not this ticket: see Gaps. | [e2e-harness.log](e2e-harness.log) |
| Screenshots and axe | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 21 screenshots (7 views × 3 Appearances), 0 axe violations. | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack.** There is no Docker daemon in this sandbox, so the backend, the twelve updated Playwright specs and `e2e/harness/axe.spec.ts` against the stack were not run. The specs type-check and lint. [shots.test.ts](shots.test.ts) stands in for the axe run: it serves the built Studio, answers the API with the unit tests' MSW fakes, and runs the same axe tags.
- **Two harness tests fail on `origin/candidate-reskin` already.** `e2e/harness/navigation.spec.ts` still checks a tab row ("Organisation settings"), but 11-11 emptied `TAB_ROWS` in `e2e/fixtures/navigation.ts`, so `openSection`/`sectionNames` open it as a switcher and time out. This branch does not touch either file (11-08 is changing the same helper concurrently), so it is left to that ticket or 11-13. The harness is not part of the merge gate.
- **Alert words differ between the list and the Agent page** until 11-08 restyles the Agent page: the list uses the design system's Badge words (Budget spent, Blocked by guardrail), the Agent page still says Budget exhausted and Block rate spike.
- **No pixel comparison.** The design canvas could not be opened from this sandbox. The comparison is against `docs/design/README.md`.
- **Concurrent tickets.** 11-06 and 11-07 add `Badge` kinds; this ticket uses the existing kinds only and does not edit `Badge.tsx`. It adds `level` to `PageHeader` in `design/content.tsx`.
