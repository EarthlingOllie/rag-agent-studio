# Evidence: ticket 12-09, Sidebar drawer on narrow screens

Branch `t/12-09`, from `claude/gallant-euler-zxqfxb` at `d302125` (spec 12's done tickets, 12-08 among them, integrated on `candidate-reskin`). The claim commit `09e1624` set Status `in-progress`. Then:

- `7ceadcf` makes the sidebar a drawer below `md`, adds its tests, the additive drawer helpers, the end-to-end drawer spec, the open drawer in the axe sweep and the **Sidebar drawer** glossary entry.
- The last commit adds this folder (scripts, logs, screenshots), ticks the criteria and sets Status done.

No backend code, API call, route or permission changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

**The button.** `design/Sidebar.tsx` `SidebarButton`: an icon button named "Open navigation" (the new `menu` icon), first in the top bar before the mark (`TopBar`'s new `menu` slot), shown below `md` only (`md:hidden`). It carries `aria-controls` (the sidebar's id) and `aria-expanded`.

**The drawer.** The sidebar itself (`design/Sidebar.tsx` `Sidebar`, used by `shell/StudioSidebar.tsx`), not a copy: closed, it is hidden below `md` as before; open, it becomes a modal dialog named "Navigation" (`role="dialog"`, `aria-modal`), fixed at the left over the page (240 px wide, full height, scrolling on its own) above a scrim. It reuses the `Dialog` focus-trap behaviour:

- opening focuses the current link (`aria-current="page"`), or the first stop when no link is current (Profile);
- Tab and Shift+Tab go round its stops and never leave it;
- Escape (unless a switcher's open menu takes it first), a press on the scrim, or following any link in it (a section or a switcher's item) closes it;
- the shell (`shell/SignedInShell.tsx`) returns focus to the button on every close.

At `md` and wider nothing changes: the button is hidden and the sidebar keeps its 12-08 layout.

**Helpers** (additive only, existing helpers untouched): `navigationButton` and `openDrawer` in `apps/studio/src/test/navigation.ts` and `e2e/fixtures/navigation.ts`.

## Test seams

- **Network seam** (`renderStudio` with MSW): `shell/SidebarDrawer.test.tsx` (new, 8 tests) covers the button in the banner and its `aria-expanded`, opening on the current link, the Tab and Shift+Tab trap, Escape, a press outside, following a link (and reopening on the new current link), no current link (Profile), the Project switcher's menu inside the drawer taking Escape first and its item closing the drawer, and the closed sidebar keeping no keys. The 12-08 `Sidebar.test.tsx` stays green unchanged. CSS (`hidden`/`md:` and the drawer's position) can't be measured in jsdom: [shots-axe.log](shots-axe.log) records it in Chrome.
- **End-to-end seam:** `e2e/tests/sidebar.spec.ts` gains the drawer journey at 390 px (hidden sidebar and full-width main, Enter opens on the current link, Tab and Shift+Tab stay inside, Escape, a press outside, a followed link, axe on the open drawer); `e2e/tests/accessibility.spec.ts` sweeps the open drawer at 390 px in both Appearances. `e2e/harness/drawer.spec.ts` checks the new Playwright helpers.

The seams were not confirmed with a human (none was available), so the spec's shared test seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | Below `md` the sidebar is hidden and an "Open navigation" button in the top bar opens it as a drawer | `SidebarDrawer.test.tsx` first test; [shots-axe.log](shots-axe.log): every `narrow-*` line reads `sidebar hidden; main 390px at 0, 0px right`, every `+drawer` line `drawer 240x844 at 0,0; button aria-expanded true`; every wide line keeps `sidebar 240px; main 1160px at 260, 20px right`. Screenshots `*-narrow-*.png` (the button left of the mark) and `*-narrow-*-drawer.png`. `sidebar.spec.ts` third test. |
| 2 | Opening focuses the current link; focus stays inside the drawer while it is open | `SidebarDrawer.test.tsx` first, third, "no current link" and switcher tests; every `+drawer` line in shots-axe.log: `focus a "<current>" (current) inside the drawer`; [keyboard-pass.log](keyboard-pass.log): "Enter opens the drawer, focus on link … (the current link)" and "Tab N times and Shift+Tab as many stay inside its N stops" on 50 page runs. |
| 3 | Escape, a press outside or following a link closes it, and focus returns to the button | `SidebarDrawer.test.tsx` Escape, outside, link and switcher tests; keyboard-pass.log: "Escape closes it, focus back on the button", "a press outside closes it…", "Enter on link … closes the drawer, focus back on the button" on every run; `sidebar.spec.ts` third test. |
| 4 | The keyboard pass and the axe sweep include the open drawer at 390 px in both Appearances | [keyboard-pass.log](keyboard-pass.log): the 25 page views × light and dark at 390×844, **problems: 0**. [shots-axe.log](shots-axe.log): 50 `+drawer` lines (25 views × `narrow-light`, `narrow-dark`), **0 violations**. The stack's sweep `accessibility.spec.ts` gains the open drawer at 390 px in both Appearances. |
| 5 | Design system only; palette ratchet passes | Token utilities only (`bg-surface`, `border-line`, `bg-scrim`, the `--ds-scrim` shadow as `Dialog` uses it, `button.iconBare`), no palette classes or `dark:`; [frontend-tests.log](frontend-tests.log) ends "0 palette-class uses under apps/studio/src (none allowed)." |
| 6 | Light and dark screenshots, wide (1440) and narrow (390), and the axe sweep in both Appearances | [screenshots/](screenshots/): the 23 signed-in pages, Require MFA enrolment and a Member of two Organisations × `-light`, `-dark`, `-narrow-light`, `-narrow-dark`, `-narrow-light-drawer`, `-narrow-dark-drawer` = 150 files. [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`, **0 violations and 0 overflows** on all 150 views. |
| 7 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage | Seams above; [frontend-tests.log](frontend-tests.log): 82 files, 1080 tests, 100% statements (4646/4646), branches (3291/3291), functions (1678/1678), lines (4067/4067). |
| 8 | New domain terms in `GLOSSARY.md`; ADRs updated if a decision changed | **Sidebar drawer** added; **Sidebar** now points to it. No decision changed: draft ADR-0014 already names the drawer (12-11 moves it into `docs/adr/`). |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `7ceadcf` (the implementation commit; this commit adds only evidence and the ticket). Each log's first line names its command and commit.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint `--max-warnings=0`, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 82 files, **1080 tests**, 100% statements, branches, functions and lines. `embed.js` 0.77 kB gzipped. 0 palette-class uses. | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` | exit 0, 16 passed (2 new drawer helper tests) | [e2e-harness.log](e2e-harness.log) |
| Changed stack specs parse | `playwright test --project=studio --list` sidebar, accessibility | exit 0, 4 tests in 2 files | [e2e-list.log](e2e-list.log) |
| Screenshots, axe, overflow, drawer, keyboard pass | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 150 page views, 0 axe violations, 0 overflows; keyboard pass 0 problems | [shots.log](shots.log), [shots-axe.log](shots-axe.log), [keyboard-pass.log](keyboard-pass.log) |

## Gaps

- **No compose stack here.** No Docker daemon was running in this sandbox for this run, so the changed stack specs (`sidebar`, `accessibility`) were listed, not run; shots.test.ts runs the same checks (drawer at 390 px, axe in both Appearances, the keyboard path) against the built Studio with the unit tests' MSW fakes. **Closed after spec 12 merged:** the whole compose-stack suite (`make e2e`'s steps, 118 tests) passed against a stack built from the integration branch, with the fixes it needed; see [SCRATCH/spec12-e2e.md](../../../../SCRATCH/spec12-e2e.md).
- **The keyboard pass is scripted** (Playwright key presses, plus one mouse press for "outside"), not a person at a keyboard; the log records each stop so a reviewer can repeat it by hand.
- **The Breadcrumb glossary entry** still calls its switchers the only navigation where the Sidebar is hidden; 12-11 rewrites the Breadcrumb and its entry, so it was left to avoid a conflict with 12-10.
- **No pixel comparison** against the design canvas.
