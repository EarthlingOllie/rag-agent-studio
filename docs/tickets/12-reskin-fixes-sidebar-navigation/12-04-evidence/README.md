# Evidence: ticket 12-04, Organisation cost reskin

Branch `t/12-04`, from `origin/candidate-reskin` at `63a7569`. The claim commit `35455a3` set Status `in-progress`. Then:

- `21780d5` is the reskin: `cost/CostPage.tsx` and its tests, the Audit page's filters on the same recipes (`settings/AuditPage.tsx`), and the `organisation-cost` and `five-minute-demo` e2e specs (the segmented control).
- `8d49bd7` updates `docs/design/README.md` (*Organisation cost*) and the `studio-reskin` patterns (a `StatCard` row as a list).
- `573bf8b` left-aligns the row names and puts a visible "Break down by" label above the control, like the date filters' labels (found in the first screenshots).
- `d5f734f` holds this folder's scripts.
- The last commit changes only this folder and the ticket file.

No backend code, route, API call, query shape or permission changes. `frontend/packages/ui` and `design/Meter.tsx` are untouched.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

- **Header.** `PageHeader` "Organisation cost" (the page's one h1) with the existing sentence as its description: "What Visitors' Conversations and Playground testing cost, at the prices frozen when each reply was made."
- **Toolbar.** "Break down by" is a `Segmented` radio group (Project / Agent), with its label shown above it like the filters beside it. From (UTC) and To (UTC) are date inputs with `field.filter` labels over `field.pill` controls, as on Conversations and Analytics. The query is unchanged: `group_by`, then `start` and `end` only when set.
- **Period line.** "2026-10-08 to 2026-11-06 (UTC days), including today so far, at the prices of the time." in `text.muted`, under the toolbar. It also shows over the empty state.
- **Summary cards.** A `layout.stats` row of three `StatCard`s, Total, Visitors and Playground, for the period. It is a list named "Spend for the period".
- **Table card.** `table.wrap`, still a focusable region named "Cost by Project" / "Cost by Agent", so it scrolls sideways inside its card on a narrow screen. Names are `table.td` row headers; the Agent breakdown's Project is `table.tdMuted`. Amounts use `table.thNumeric` / `table.tdNumeric`: right-aligned, mono. The total row ("All Projects" / "All Agents") is set apart on `sunken` above a `line` border, in medium weight.
- **States.**
  - Nothing spent: `EmptyState` (analytics icon) "Nothing was spent in this period", with "Visitors' Conversations and Playground testing in any Project show up here, with what they cost."
  - Bad dates (the API's 422): `Notice tone="error"` with the existing message, "Check the dates: From can't be after To, and the period can be at most 366 days." A failed load is the same notice with "The cost could not be loaded. Try again shortly."
  - Loading: `Skeleton` named "Loading the cost".
- **Editors.** Under the header, an `EmptyState` "Only Owners see the Organisation's spend" with "Ask an Owner of this Organisation if you need to know what it spent." No filters, and the cost is never requested.
- **Audit filters.** The Audit page's own `FILTER` string is now `field.pill`, and its labels `field.filter`, as the spec's Organisation cost module asks.

### Moved behaviour

| Before | After |
| --- | --- |
| "Break down by" `<select>` (Project / Agent) | `Segmented` radio group "Break down by" (radios Project / Agent; arrow keys move the choice) |
| "Loading the cost…" text | `Skeleton`, status "Loading the cost" |
| "Nothing was spent in this period." text | `EmptyState` heading "Nothing was spent in this period" with a description |
| Editor: "Only Owners can see what the Organisation spends." text | `EmptyState` heading "Only Owners see the Organisation's spend" with a description |
| Errors: red text (`role="alert"`) | `Notice tone="error"` (still `role="alert"`, same words) |

## Test seams

These are the spec's network seam (`renderStudio` with MSW) and the e2e spec. The tests were changed red first (5 of 6 failing), then made green.

- `cost/CostPage.test.tsx`:
  - the header's description, the summary cards' figures (`Total $12.51`, `Visitors $12.50`, `Playground $0.0042`), the "Break down by" radio group (Project checked) and the scrollable region;
  - choosing Agent by clicking the radio, and back to Project with the arrow key, checking the query each time;
  - the dates and the 422 message as an alert (unchanged, still green);
  - the empty state's heading and description, with the period line and without cards or table;
  - the loading placeholder (status "Loading the cost") and the load error;
  - the Editor's state: its heading and description, no filters, no table, no request.
- `settings/AuditPage.test.tsx` is unchanged and still passes: the filters keep their labels.
- `e2e/tests/organisation-cost.spec.ts` clicks the Agent radio and checks the three summary cards; `five-minute-demo.spec.ts` clicks the Agent radio.

The seams were not confirmed with a human (none was available), so the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | Page header (Organisation cost) whose description is the existing sentence about frozen prices | `PageHeader` in `CostPage.tsx`. Test "an Owner sees what each Project cost…" checks the h1 and the sentence. Screenshots `cost-by-project-*`. |
| 2 | "Break down by" is a segmented control (Project / Agent); From and To are date filters styled like Conversations and Analytics | `Segmented` with `BREAKDOWNS`; `field.filter` / `field.pill`, the same recipes `AnalyticsTab.tsx` and `ConversationsTab.tsx` use. Tests: the radio group and its options; "the Owner breaks the cost down by Agent…" (click and arrow key); "the Owner chooses the period…". Screenshots `cost-by-project-*`, `cost-by-agent-*`. |
| 3 | Summary cards show the total, Visitor and Playground spend; the period line sits under the toolbar | `CostStats` (`StatCard` ×3 in `layout.stats`). Tests check `["Total$12.51", "Visitors$12.50", "Playground$0.0042"]` by Project and by Agent, and the period line. Screenshots show the line between the toolbar and the cards. |
| 4 | Table card, amounts right-aligned in mono, total row set apart; on a narrow screen it scrolls inside its card and the page doesn't | `table.wrap` region (tabindex 0), `table.thNumeric` / `table.tdNumeric`, `tfoot` row on `sunken` above a border. Tests check the region and every cell. [shots-axe.log](shots-axe.log): "horizontal scroll: no" for every view at 390 wide. Screenshots `cost-by-agent-narrow-*`. |
| 5 | Nothing spent: designed empty state; bad dates: the existing message as an error notice; loading: a placeholder | `EmptyState`, `Notice tone="error"`, `Skeleton`. Tests "a period with no spending says so", "the Owner chooses the period…", "the page says so while the cost loads…". Screenshots `cost-nothing-spent-*`, `cost-bad-dates-*`, `cost-loading-*`. |
| 6 | Editors see a designed state saying only Owners see the Organisation's spend | `EmptyState` "Only Owners see the Organisation's spend". Test "Owners find the cost page in the navigation; Editors neither see it nor can open it". Screenshots `cost-editor-*`. |
| 7 | Design system only, no palette classes or `dark:`; the palette ratchet passes | Only `../design` recipes and components; the one local class string is `TOTAL_ROW` (`border-line`, `bg-sunken`, tokens). [frontend-tests.log](frontend-tests.log): "0 palette-class uses under apps/studio/src (none allowed)." |
| 8 | Light and dark screenshots, wide (1440) and narrow (390), and the axe sweep in both Appearances | [screenshots/](screenshots/): 7 views (by Project, by Agent, nothing spent, bad dates, loading, Editor, Audit) × wide and narrow × light, dark (system) and chosen dark = 42 images. [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`, **0 violations**, no horizontal scroll. |
| 9 | Tests at the highest seam; 100% line and branch coverage holds | Seams above. [frontend-tests.log](frontend-tests.log): `make test-frontend` at 100% statements, branches, functions and lines. |
| 10 | New domain terms in `GLOSSARY.md`; ADRs updated if a decision changed | No new domain term (Organisation, Owner, Editor, Visitor, Playground and Cost are already defined). No decision changed; the design README's *Pages* gains the Organisation cost layout. |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `d5f734f`, which is `origin/candidate-reskin` (`63a7569`) plus this branch. Each log's first line names its command and commit. GitHub Actions is not used, so these are local.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 79 files, 1035 tests, 100% statements (4558/4558), branches (3230/3230), functions (1645/1645) and lines (3987/3987). `embed.js` is 0.77 kB gzipped. 0 palette-class uses (none allowed). | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` (Chrome) | exit 0, 12 passed | [e2e-harness.log](e2e-harness.log) |
| Screenshots and axe | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 42 screenshots, 0 axe violations, no horizontal scroll. | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack.** There is no Docker daemon in this sandbox, so the backend, the `organisation-cost` and `five-minute-demo` Playwright specs and `e2e/harness/axe.spec.ts` against the stack were not run. The specs type-check and lint. [shots.test.ts](shots.test.ts) stands in for the axe run: it serves the built Studio, answers the API with the unit tests' MSW fakes, and runs the same axe tags. No backend code changed.
- **No pixel comparison** with the design canvas, which could not be opened from this sandbox. The comparison is against `docs/design/README.md`, the review notes in `docs/reviews/candidate-reskin/README.md` §2 and the patterns.
- **Concurrent tickets.** 12-07 removes the `BUTTON` / `INPUT` strings; this page no longer imports them. 12-08 moves Cost into the sidebar; the Editor test's breadcrumb assertion will move with it there.
