# Evidence: ticket 12-11, Plain breadcrumb, account menu cleanup and docs

Branch `t/12-11`, from `t/12-09` (`6f5e70b`, the sidebar drawer) with `t/12-10` (`6af8a27`, Agent view tabs) merged in `322957f` (no conflicts); both are built on `claude/gallant-euler-zxqfxb` at `d302125`, which holds 12-08. The frontend checks passed on the merge before any 12-11 change. The claim commit `58563de` set Status `in-progress`. Then:

- `6608c5a`: the breadcrumb becomes plain links, the account menu is the only home of Profile and Security, the 1–6 hints go, and Organisation settings' areas move to a tab row (tests first: the new shell, Agent, Document and `Breadcrumb` tests failed before the code).
- `2580026`: ADR-0014 moves into `docs/adr/`; the design README and GLOSSARY describe the sidebar.
- `9807b09`: the first screenshot run showed the top bar three rows high at 390 px on a Project page (the mark, then the path, then the toggle and avatar); now the mark and the two crumbs share one row.
- The last commit adds this folder, ticks the criteria and sets Status done.

No backend code, API call, route or permission changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

**Plain breadcrumb** (`design/Breadcrumb.tsx`: `Breadcrumb`, `crumbLink`; `shell/StudioBreadcrumb.tsx`). The crumbs are router links with no menus, from the Organisation's page the Member is under to the page they are on: `Projects`, `Cost`, `Security`, `Profile`; `Settings / Members`; `HR handbook / Documents`; `HR handbook / Documents / handbook.pdf`; `HR handbook / Agents / HR helper` (the Agent stays the last crumb on all four of its views). Only the last crumb carries `aria-current="page"`: each crumb is a `createLink` anchor whose `current` prop replaces the router's own marking, which would also mark the Project's crumb on its Documents page. The Organisation is not a crumb (the sidebar names it). Below `md` `Breadcrumb` shows only the last two crumbs (and drops the separator before the first one shown); `PathFold` ("…", "Show the whole path"), `CrumbSwitcher`, `CrumbText`, `crumbClass`, `OrganisationCrumb` and `SettingsCrumb` are gone.

**Account menu cleanup.** The breadcrumb's "Organisation sections" switcher, the second home of Security and Profile, is gone, so Profile, Security and Sign out are only in the account menu (`shell/AccountMenu.tsx`, unchanged). The Project sections' 1–6 hints went with the section switcher, and `MenuItem.hint` with them.

**Organisation settings tab row.** The areas (General, Credentials, Models, Theme, and Members and Audit for Owners) were offered only by the breadcrumb's Settings switcher; they are now a `TabRow` "Organisation settings" under the settings header (`settings/OrganisationSettings.tsx`, areas in `shell/settingsNavigation.tsx`, shared with the breadcrumb), like an Agent's views. ADR-0014 records this.

**Top bar on a phone** (`design/TopBar.tsx`). The mark, the menu button and the path no longer wrap: the path is cut short with an ellipsis, and the mark shows only the wave below `md` (`Brand compact`; the home link is still named "Studio home"). The page's own actions join the row while it leaves the path 12rem, and drop under it otherwise.

**Navigation helpers** (`apps/studio/src/test/navigation.ts`, `e2e/fixtures/navigation.ts`). "Organisation settings" now reads the tab row (a list of links, like "Agent views"); a new `breadcrumb()` returns the crumbs shown and the current one. Names and vocabulary are unchanged, so the existing `openSection(…, "Organisation settings", …)` specs keep working.

**Docs.** `docs/adr/0014-sidebar-navigation.md` (moved from `docs/reviews/candidate-reskin/`, plus a closing paragraph on the two details settled while building it); ADR-0013 notes the amendment; the spec and the review link to the new place. The design README: principle 3 ("Navigation you can see"), the layout sketch, "Navigation: the sidebar" with the navigation table, and "Navigation: the breadcrumb" replacing the switcher section; the components table, the accent list and the Don't list follow. GLOSSARY: Breadcrumb is a plain path; Sidebar mentions the account menu and the settings tab row; Project section, Agent view, Organisation and Document viewer lose the switcher wording.

## Test seams

- **Network seam** (`renderStudio` with MSW): `shell/SignedInShell.test.tsx` (the plain path and its current crumb on the Projects list, a Project, a section and back up; no fold on a long path; the settings tab row and its crumbs, an Editor's tabs, an unknown settings address; a Project that can't be loaded; Profile, Security and Sign out only in the account menu, their pages the current crumb; Cost; no number hints), `projects/AgentViews.test.tsx` (the Agent as the last crumb on its views, back up to Agents; an Agent that can't be found ends at Agents), `projects/DocumentViewer.test.tsx` (the Document's crumb after the Documents crumb that leads back), `design/Breadcrumb.test.tsx` (links in order, hidden separators, no buttons; the last two crumbs below `md`), `design/content.test.tsx` (`Brand compact`). Settings tests (`MembersPage`, `AuditPage`, `ThemePage`, …) now open areas through the tab row via the unchanged helper.
- **End-to-end seam:** `e2e/tests/sidebar.spec.ts` gains "the breadcrumb is a plain path of links, and on a phone shows only its last two crumbs on one row" (crumbs, no buttons, the account menu, a crumb leading back, 390 px: two crumbs, one line, no sideways scroll, axe). It is listed and type-checked, not run (no stack; see Gaps). The harness (`e2e/harness/navigation.spec.ts`, `agent-navigation.spec.ts`) drives the rewritten helpers against stand-in pages with a plain breadcrumb and a settings tab row, and passes.
- **Browser:** [shots.test.ts](shots.test.ts) serves the built Studio with the unit tests' MSW fakes in Chrome and records, on every page of the axe sweep's list plus the open account menu, the crumbs shown, the current crumb, buttons in the breadcrumb, the top bar's height and the settings tabs ([shots-axe.log](shots-axe.log)).

The seams were not confirmed with a human (none was available), so the spec's shared test seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | The breadcrumb's crumbs are plain links with no menus; the current crumb is marked `aria-current="page"` | `SignedInShell.test.tsx` "the breadcrumb is a plain path of links with no menus; the current crumb is the page" and the settings, Project, Profile/Security and Cost tests; `AgentViews.test.tsx` "the breadcrumb is the Project, Agents and the Agent…"; `DocumentViewer.test.tsx`; `Breadcrumb.test.tsx`. [shots-axe.log](shots-axe.log): every one of 96 page views has `breadcrumb buttons 0` and exactly one crumb marked `*` (none on the unknown address, which is not in the sweep). |
| 2 | Below `md` the breadcrumb shows only its last two crumbs; the "…" fold is gone | `Breadcrumb.test.tsx` "below md keeps only the last two crumbs…"; `SignedInShell.test.tsx` "there is no fold…"; shots-axe.log at 390 px: `crumbs [Agents / HR helper*] (1 hidden)`, `[Documents / handbook.pdf*] (1 hidden)`, two crumbs or fewer everywhere; `*-narrow-*.png`. Top bar 61 px (one row) on every narrow page without actions of its own. |
| 3 | Profile, Security and Sign out are only in the account menu; the 1–6 number hints are gone | `SignedInShell.test.tsx` "Profile, Security and Sign out are only in the account menu…" (no link or menu item of those names elsewhere) and "no navigation item carries a number hint"; `Sidebar.test.tsx` (unchanged: the sidebar has none of them outside the Require MFA policy); shots-axe.log `account menu [Profile, Security, Sign out]`; `account-menu-open-*.png`. `MenuItem.hint` is removed. |
| 4 | Draft ADR-0014 moves into `docs/adr/`; the design README's principle 3, navigation table and breadcrumb section describe the sidebar | [docs/adr/0014-sidebar-navigation.md](../../../adr/0014-sidebar-navigation.md) (git rename from `docs/reviews/candidate-reskin/`); [design README](../../../design/README.md) principle 3, *Layout*, *Navigation: the sidebar* (with the table), *Navigation: the breadcrumb*; [link-check.log](link-check.log): every link resolves. |
| 5 | GLOSSARY: Breadcrumb is a plain path; Breadcrumb fold and Crumb switcher are removed; Sidebar and Sidebar drawer are added | [GLOSSARY.md](../../../../GLOSSARY.md) **Breadcrumb** (plain path; "Breadcrumb switcher" and "crumb menu" under _Avoid_). The fold and the crumb switchers were never entries of their own: they were the Breadcrumb entry's switcher and "…" wording, which is gone from it and from Project section, Agent view, Organisation and Document viewer. **Sidebar** and **Sidebar drawer** were added by 12-08 and 12-09 and are kept. |
| 6 | Design system only; palette ratchet passes | `Breadcrumb`/`crumbLink`, the settings `TabRow`/`tabLink` and `Brand compact` use tokens and recipes only (`text-muted`, `aria-[current=page]:text-accent`, `hover:bg-sunken`); [frontend-tests.log](frontend-tests.log) ends "0 palette-class uses under apps/studio/src (none allowed)." The README's components table lists them. |
| 7 | Light and dark screenshots, wide (1440) and narrow (390), and the axe sweep in both Appearances | [screenshots/](screenshots/): 10 views (Projects, Cost, settings General and Members, Profile, a Project's Documents, the Document viewer, an Agent's Versions and Conversation, the account menu open) × `-light`, `-dark`, `-narrow-light`, `-narrow-dark` = 40 files. [shots-axe.log](shots-axe.log): all 23 pages of the sweep's list plus the account menu, × 4 = 96 views, tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`: **0 violations, 0 overflows, 0 breadcrumb buttons**. |
| 8 | Tests at the highest seam; 100% line and branch coverage | Seams above; [frontend-tests.log](frontend-tests.log): 83 files, 1082 tests, 100% statements (4615/4615), branches (3255/3255), functions (1666/1666), lines (4039/4039). |
| 9 | New domain terms in `GLOSSARY.md`; ADRs updated if a decision changed | Breadcrumb redefined; the settings tab row is described under Sidebar. ADR-0014 gains the two decisions made while building (the path starts below the Organisation; Organisation settings' areas are a tab row) and ADR-0013 notes that ADR-0014 amends it. |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `9807b09` (the last code commit; the evidence commit adds only this folder and the ticket). Each log's first line names its command and commit.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint `--max-warnings=0`, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 83 files, **1082 tests**, 100% statements, branches, functions and lines. `embed.js` 0.77 kB gzipped. 0 palette-class uses. | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0, 2623 links resolve | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` | exit 0, 20 passed (2 new, 2 rewritten) | [e2e-harness.log](e2e-harness.log) |
| Changed and affected stack specs parse | `playwright test --project=studio --list …` | exit 0, 10 tests in 5 files | [e2e-list.log](e2e-list.log) |
| Screenshots, axe, overflow, crumbs | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 96 page views, 0 axe violations, 0 overflows, 0 breadcrumb buttons | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose-stack run.** The Docker daemon isn't running in this sandbox, so the new `sidebar.spec.ts` test and the specs that open Organisation settings areas (`members`, `require-mfa`, …, now through the tab row by the same helper call) were listed and type-checked but not run against the stack; the harness and the browser run above stand in.
- **Agent pages on a phone are two rows.** The path and the mark fit one row everywhere; an Agent's own top bar actions (saved state, History, Publish) drop to a second row, as before this ticket. Pages without actions of their own are one row (61 px).
- **Tight paths are cut short.** At 390 px a long pair such as `Documents / handbook.pdf` shows as `Docum… / handboo…`; the full names are in the link text for assistive technology and on wider screens.
- **The `studio-reskin` skill** (`.claude/skills/studio-reskin/PATTERNS.md`) still describes the breadcrumb switchers of 11-04; it was left for whoever next edits the skill, as this ticket's criteria name the design README and GLOSSARY.
- **No pixel comparison** against the design canvas.
