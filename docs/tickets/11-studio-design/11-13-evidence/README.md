# Evidence: ticket 11-13, Polish: narrow screens, accessibility and screenshots

Branch `ticket/11-13-polish-narrow-a11y-screenshots`, from `origin/candidate-reskin` at `4da508d` (the merge of 11-10, #93). The claim commit `543f288` set Status `in-progress`. Then:

- `0f4712b` takes the palette count to zero and deletes `frontend/palette-baseline.json` (the ratchet is now "none allowed").
- `e23c9a2` folds the breadcrumb's middle crumbs into "…" on narrow screens (with `SignedInShell.test.tsx` tests).
- `3299dfe` adds the axe sweep of every signed-in page in light and dark (`e2e/tests/accessibility.spec.ts`), its page list (`e2e/fixtures/pages.ts`) and `signedInPages.test.ts`, which keeps the list in step with the router.
- `d0e8056` and `d8bc4bc` fix what the keyboard pass and the narrow axe run found (focus rings; focusable scroll boxes; tables widening the page; the fold's width). `e80d346` adjusts two names after the full test run.
- `84cfaf0` updates `GLOSSARY.md`, `docs/design/README.md` and `docs/development.md`. `f9d73cf` removes the navigation helpers' tab-row fallback and its two harness specs, which had failed since the last tab row went (11-06 onwards).
- `4e79a2d` adds this folder's scripts (`fa89983` adds the Organisation switcher to the keyboard pass). The last commit changes only this folder, `docs/screenshots` and the ticket (the logs and screenshots of the run, Status done).

No backend code, API call, route or permission changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

**Palette count zero.** The 15 remaining matches were not classes: comments in `tokens.css` that named `slate-700` and `red-800`, and object keys named `dark` (a Theme colour's `{ light, dark }` in `AgentBranding.tsx` and the test fakes). The ratchet's pattern now counts the `dark:` *variant* only, `dark:` directly followed by a class (`dark:bg-black`, `dark:[…]`, `dark:!p-0`); a new `ratchet.test.mjs` case pins both sides. The comment is reworded. The count is 0, `palette-baseline.json` is deleted, and the check reports "0 palette-class uses under apps/studio/src (none allowed)"; any palette class now fails it (the existing "with no baseline file none are allowed" test).

**Narrow screens** (`design/Breadcrumb.tsx`). Below `md` (768px) a path of three or more crumbs shows the Organisation, a "…" button (named **Show the whole path**, `aria-expanded`) and the current page. The button opens **The whole path**, a popover list of the folded crumbs, each still its switcher. Escape closes it and returns focus to "…" (an Escape inside a switcher's own menu closes only that menu); a press outside, or following a link inside it, closes it too. It is placed against the breadcrumb and kept inside the window. Pages register nothing: every breadcrumb gets it. On wider screens nothing changes. The top bar already wrapped; at 390px it is two rows (mark and path, then the toggle and avatar).

Also from the narrow run: a table inside `table.wrap` widened the page through a screen-reader-only label placed against the page, so `table.wrap` is now `relative`; the tables and code that scroll sideways without anything focusable inside (Audit Events, Cost, the Version comparison, the chart's Table view, code blocks) are named regions with `tabIndex=0`, so the keyboard can scroll them (axe `scrollable-region-focusable`).

**The axe sweep** (`e2e/tests/accessibility.spec.ts`, stack project). One Member sets a Default Model, makes a Project, an Agent with a Live Version, a Playground Conversation and a Document, then visits every page in `SIGNED_IN_PAGES` (`e2e/fixtures/pages.ts`, 23 pages) with `emulateMedia({ colorScheme })` light then dark, waits for the `h1`, and runs axe with the shared WCAG 2.2 AA tags; the expectation lists any violations by Appearance and page. `apps/studio/src/signedInPages.test.ts` walks the router's route tree and fails when a signed-in page is missing from (or doubled in) that list.

**Keyboard focus.** The keyboard pass found four stops without a visible focus indicator: the Documents search box and the Playground's question (their inputs draw no outline; their pill draws only a 1px border change) and the date filters (Chrome focuses a field inside the input, which `:focus-visible` doesn't reach). The search pill and the composer now draw the accent ring around their box, and `tokens.css` rings a date or time input while a field inside it has focus.

### Moved actions (behaviour otherwise unchanged)

| Before | After |
| --- | --- |
| On a narrow screen the whole breadcrumb wrapped over several lines | The middle crumbs are behind "…" (Show the whole path); the Organisation and the current page stay |

Nothing else moved. Routes, API calls, permissions and accessible names are unchanged, apart from the new names: the "…" button, its list, and the scroll regions (each named like its table, or "<label> code").

## Test seams

- **Network seam** (`renderStudio` with MSW): `shell/SignedInShell.test.tsx` gains "on a narrow screen the middle crumbs fold into a … menu; the Organisation and the current page stay" (the button and its name, the folded crumbs only, Escape, Escape inside a switcher, following a switcher's link, a press outside) and "a breadcrumb of two crumbs has nothing to fold". Written red first. CSS hiding can't be seen in jsdom: [shots-axe.log](shots-axe.log) records the visible crumbs at 390px and at 1280px. The Audit, Cost, Analytics, chart and code block tests assert their focusable scroll regions (written red first).
- **Router seam:** `signedInPages.test.ts` (checked to fail when a page is removed from the list).
- **Script seam:** `ratchet.test.mjs` (Node's 100% coverage gate) gains the `dark` key case, written red first.
- **End-to-end seam:** `e2e/tests/accessibility.spec.ts` is new; it lists, type-checks and lints ([e2e-list.log](e2e-list.log), [lint.log](lint.log)) but was not run (no stack). The `harness` project passes ([e2e-harness.log](e2e-harness.log)).

The seams were not confirmed with a human (none was available), so the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | The latest `candidate` is merged in and any feature UI it brings is reskinned, so `candidate-reskin` can merge back into `candidate` cleanly | `origin/candidate` (`d79dd3f`) is already an ancestor of `origin/candidate-reskin` (`git merge-base --is-ancestor origin/candidate HEAD` succeeds; `git log origin/candidate-reskin..origin/candidate` is empty), so there is nothing new to merge or reskin, and merging `candidate-reskin` into `candidate` is a fast-forward of `candidate`'s history. Checked at the start of the ticket and again before the PR. |
| 2 | The palette count is zero; the ratchet becomes "none allowed" and the baseline file is deleted | `frontend/palette-baseline.json` deleted; [frontend-tests.log](frontend-tests.log) ends "0 palette-class uses under apps/studio/src (none allowed)." |
| 3 | On narrow screens the breadcrumb collapses its middle crumbs into a menu and keeps the Organisation and the current page | Tests above. [shots-axe.log](shots-axe.log): every `narrow-*` line's crumbs are `[Analytical Engines / Show the whole path / <current>]` on pages three or more deep, with 0px horizontal overflow; screenshots `*-narrow-light.png`, `*-narrow-dark.png`, `agent-versions-fold-open-narrow-*`. [keyboard-pass.log](keyboard-pass.log) "narrow:" section. |
| 4 | The axe harness runs every signed-in page in light and dark | `e2e/tests/accessibility.spec.ts` over `e2e/fixtures/pages.ts`, kept complete by `signedInPages.test.ts`. Run here against the built Studio: [shots-axe.log](shots-axe.log), the same 23 pages (and the 7 signed-out ones) in light, dark and chosen dark at 1280px and light and dark at 390px, **0 violations**. |
| 5 | `docs/screenshots` is recaptured in both Appearances | [docs/screenshots](../../../screenshots/README.md): `63-` to `86-`, 24 screens × light and dark (48 files), the README's new first section. |
| 6 | A keyboard-only pass of every switcher, menu and dialog is recorded in the evidence | [keyboard-pass.log](keyboard-pass.log): all 23 signed-in pages tabbed through from the top (the Tab order of each is listed), every menu met on the way (every switcher, the account menu and every ⋯ menu) opened with Enter, walked with End, Home and ArrowDown and closed with Escape with focus returned; a switcher's link followed with keys; the Organisation switcher (with Ada in two Organisations); the Appearance toggle; 8 dialogs opened from a button or a ⋯ menu item with Tab and Shift+Tab kept inside and Escape returning focus; the narrow fold. 402 checks, 0 problems. |
| 7 | Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR | The moved-actions table above (and in the PR). All 1035 Studio tests pass. |
| 8 | The palette ratchet baseline is lowered to the new count | 15 → **0**, and the file deleted (criterion 2). |
| 9 | Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas | [screenshots/](screenshots/): every page (the breadcrumb and focus changes touch them all) as `-light`, `-dark`, `-chosen-dark`, `-narrow-light` and `-narrow-dark`, 152 files. Layout per `docs/design/README.md` (*Navigation*, narrow screens). |
| 10 | axe reports zero AA violations on the changed pages in both Appearances | [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`; **0 violations** and 0 overflows on all 152 page views. The first narrow run found 6 `scrollable-region-focusable` violations and 5 overflowing pages, fixed in `d8bc4bc`. |
| 11 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams above; [frontend-tests.log](frontend-tests.log): 100% statements (4556/4556), branches (3228/3228), functions (1643/1643) and lines (3985/3985). |
| 12 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | **Breadcrumb** gains the narrow-screen fold ("Show the whole path"); **Palette ratchet** now reads "none allowed" and says a `dark` key is not counted. No ADR decision changed (ADR-0013 already sets one top bar and tokens only). |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `fa89983`, which contains the latest `origin/candidate-reskin` (`4da508d`). Each log's first line names its command and commit. GitHub Actions is down, so these are local.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 79 files, **1035 tests**, 100% statements, branches, functions and lines. `embed.js` is 0.78 kB gzipped. 0 palette-class uses (none allowed). | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` | exit 0, 12 passed | [e2e-harness.log](e2e-harness.log) |
| The new axe sweep parses | `playwright test --project=studio --list e2e/tests/accessibility.spec.ts` | exit 0, 1 test | [e2e-list.log](e2e-list.log) |
| Screenshots, axe, overflow, keyboard pass, docs/screenshots | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 152 page views, 0 axe violations, 0 overflows; keyboard pass 0 problems; 48 docs screenshots. | [shots.log](shots.log), [shots-axe.log](shots-axe.log), [keyboard-pass.log](keyboard-pass.log) |

## Gaps

- **No compose stack.** There is no Docker daemon here, so the backend and `e2e/tests/accessibility.spec.ts` (and the rest of the stack suite) were not run. The spec lists, type-checks and lints. [shots.test.ts](shots.test.ts) stands in for it: it serves the built Studio, answers the API with the unit tests' MSW fakes, and runs the same axe tags over the same page list.
- **docs/screenshots use the tests' data,** not the seeded demo's, for the same reason; the README says so and how to recapture. The earlier seeded sets are kept below the new section as a record.
- **The keyboard pass is scripted** (Playwright key presses only, no mouse), not a person at a keyboard; it records each stop and check, so a reviewer can repeat it by hand from the log.
- **The repository's `studio-reskin` skill** (`.claude/skills/studio-reskin`) still tells a slice to commit a lowered `palette-baseline.json` and mentions `TAB_ROWS`; it is agent configuration, which this ticket leaves alone. The design README and the development notes say the current rule.
- **The CI workflow's comment** above the ratchet step (`.github/workflows/frontend.yml`) still describes the baseline; the step itself (`pnpm palette-ratchet`) is unchanged and now enforces none allowed. Workflow files were left alone so the branch pushes without workflow scope.
- **No pixel comparison.** The design canvas could not be opened from this sandbox; the comparison is against `docs/design/README.md` and the patterns.
