# Evidence: ticket 12-10, Agent view tabs

Branch `t/12-10`, from `claude/gallant-euler-zxqfxb` at `d302125` (spec 12's done tickets, 12-08 among them, integrated on `candidate-reskin`). The claim commit `d5a324d` set Status `in-progress`. Then:

- `9467dc6` adds the tab row, the ▾ Agent switcher and the single h1, leaves out the Project's header on Agent pages, teaches the navigation helpers (Testing Library and Playwright) to read Agent views from the tab row, moves the Agent end-to-end specs to the Agent's h1, and updates the design README and GLOSSARY.
- `f317ade`: the first screenshot run showed the open Agent switcher running 17 px past a 390 px screen; the menu now drops from the start of the title's line.
- The last commit adds this folder, ticks the criteria and sets Status done.

No backend code, API call, route or permission changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

**Tab row** (`design/TabRow.tsx`: `TabRow`, `tabLink`). Under the Agent's header, a navigation landmark named "Agent views" holding a list of four links: Playground, Versions, Embed & limits, Conversations (`AgentViewTabs` in `projects/AgentPage.tsx`). The current one carries `aria-current="page"` (an `accent` underline, `ink` text); Conversations stays current on a Conversation opened from it. The router's own prefix marking is turned off (`exact`), as in the sidebar, so Playground is not current on every view. On a narrow screen the row scrolls sideways inside its own width instead of wrapping or widening the page.

**One h1.** The Agent's header is now its `PageHeader` (level 1, so the Agent's name is the page's h1); `PageHeader` gains `headingId` (the header stays a region named after the Agent) and `beside` (what sits on the title's line: the ▾ and the Live / Draft badges). `ProjectLayout` (`projects/ProjectPage.tsx`) leaves out the Project's `PageHeader`, Edit details and ⋯ menu on every Agent route; on an archived Project the "This Project is archived" notice stays above the Agent.

**Agent switcher.** A ▾ (`button.iconBare`, the `chevronDown` icon) after the name opens a `Menu` "Agents" of the Project's open Agents, the current one marked; the button is named "HR helper, Agents", like the other switchers. The Agent views and switcher items moved into `shell/projectNavigation.tsx` (`AGENT_VIEWS`, `useAgentViews`, `useAgentSwitcherItems`), shared with the breadcrumb, whose switchers stay until 12-11 makes it plain.

**Navigation helpers** (`apps/studio/src/test/navigation.ts`, `e2e/fixtures/navigation.ts`). Additive: `openSection`, `sectionNames`, `currentSection` and `hasMenu` keep their names and vocabulary; "Agent views" now reads the tab row (a list of links, like a sidebar group) and "Agents" the switcher in the page's `main`. An `agentTabs` locator is added to each.

## Test seams

- **Network seam** (`renderStudio` with MSW): `projects/AgentViews.test.tsx` (the tab row, its order, links and current tab; the helpers reading it; the one h1 without the Project's header; the ▾ switcher listing and switching; an Agent that can't be listed or found; the breadcrumb's view switcher still offering the same views until 12-11); `ConversationsAnalytics.test.tsx` (Conversations stays the current tab on a Conversation opened from it); `ProjectPage.test.tsx` (the Project header is left out on an Agent and returns on the Agents list; an archived Project's Agent keeps the archived notice); `design/content.test.tsx` (`PageHeader`'s `beside` and `headingId`). Existing Agent tests now find the Agent's name at level 1.
- **End-to-end seam:** `e2e/harness/agent-navigation.spec.ts` (new) drives the rewritten Playwright helpers against a stand-in Agent page that still has the breadcrumb's switchers of the same names, and passes ([e2e-harness.log](e2e-harness.log)). The Agent specs (`agent-*`, `embed`, `playground`, `rate-limits`, `token-budget`, `operational-settings`, `five-minute-demo`, `sidebar`) look for the Agent's name as the h1 and still parse and type-check ([e2e-list.log](e2e-list.log), [lint.log](lint.log)).
- **Browser:** [shots.test.ts](shots.test.ts) serves the built Studio with the unit tests' MSW fakes in Chrome and records the h1s, the tab row and the switcher on every Agent page ([shots-axe.log](shots-axe.log)).

The seams were not confirmed with a human (none was available), so the spec's shared test seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | Playground, Versions, Embed & limits and Conversations are a tab row under the Agent's header; the current one is marked, and stays marked on a Conversation opened from it | `AgentViews.test.tsx` "the Agent's views are a tab row under its header, the current one marked"; `ConversationsAnalytics.test.tsx` "the Agent's Conversations view is the same list…" (Conversations current after opening one); [shots-axe.log](shots-axe.log) `tabs [Playground*, …]`, `Versions*`, `Embed & limits*`, `Conversations*` on `agent-conversations` and `agent-conversation`; screenshots `agent-*.png`. |
| 2 | The Agent's name carries a ▾ that switches to another of the Project's Agents | `AgentViews.test.tsx` "the ▾ on the Agent's name lists the Project's open Agents and switches between them"; shots-axe.log `▾ "HR helper, Agents" open [HR helper, Pay helper]`; `agent-switcher-open-*.png` (also narrow, no overflow). |
| 3 | Agent pages no longer show the Project's page header; the Agent's name is the page's h1 | `AgentViews.test.tsx` "the Agent's name is the page's one h1…"; `ProjectPage.test.tsx` two new tests; shots-axe.log `h1s [HR helper]` (one h1) on every Agent page and `h1s [HR handbook]` on the Agents list. |
| 4 | The navigation helpers read Agent views from the tab row | Both helpers' "Agent views" branch reads the "Agent views" landmark; `AgentViews.test.tsx` "the navigation helpers read the Agent's views from the tab row"; harness `agent-navigation.spec.ts` "Agent views are read from the tab row, not the breadcrumb's view switcher" ([e2e-harness.log](e2e-harness.log), 16 passed). |
| 5 | Design system only; palette ratchet passes | `TabRow`/`tabLink` and the switcher use tokens and recipes only (`border-line`, `text-muted`, `aria-[current=page]:border-accent`, `button.iconBare`); [frontend-tests.log](frontend-tests.log) ends "0 palette-class uses under apps/studio/src (none allowed)." `TabRow` is listed in the design README's components table and the Agent page section describes it. |
| 6 | Light and dark screenshots, wide (1440) and narrow (390), and the axe sweep in both Appearances | [screenshots/](screenshots/): 8 views (the five Agent pages of the sweep's list, an archived Agent, the switcher open, the Agents list) × `-light`, `-dark`, `-narrow-light`, `-narrow-dark` = 32 files. [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`, **0 violations and 0 overflows** on all 32. |
| 7 | Tests at the highest seam; 100% line and branch coverage | Seams above; [frontend-tests.log](frontend-tests.log): 81 files, 1078 tests, 100% statements (4625/4625), branches (3269/3269), functions (1678/1678), lines (4049/4049). |
| 8 | New domain terms in `GLOSSARY.md`; ADRs updated if a decision changed | **Agent view** now says the views are a tab row under the Agent's header, the name is the page's one heading and the ▾ is the Agent switcher. No new decision: draft ADR-0014 already records the Agent tabs and the single h1, and 12-11 moves it into `docs/adr/` with the design README's principle 3 and navigation table. |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `f317ade` (the last code commit; the evidence commit adds only this folder and the ticket). Each log's first line names its command and commit.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint `--max-warnings=0`, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 81 files, **1078 tests**, 100% statements, branches, functions and lines. `embed.js` 0.77 kB gzipped. 0 palette-class uses. | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0, 2574 links resolve | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` | exit 0, 16 passed (2 new) | [e2e-harness.log](e2e-harness.log) |
| Changed stack specs parse | `playwright test --project=studio --list …` | exit 0, 12 tests in 11 files | [e2e-list.log](e2e-list.log) |
| Screenshots, axe, overflow, h1s and tabs | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 32 page views, 0 axe violations, 0 overflows | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

The open-switcher views run axe without `target-size`: on a phone the open menu covers the ⋯ button that wraps under the title, which that rule reports as obscured (any open popover would be). Every other rule runs on them, and the same page with the menu closed (`agent-playground`) passes every rule.

## Gaps

- **No compose-stack run.** The Docker daemon isn't running in this sandbox, so the Agent specs were listed and type-checked but not run against the stack; the harness and the browser run above stand in. The changes to them are one locator each (the Agent's name at level 1 instead of 2). **Closed after spec 12 merged:** the whole compose-stack suite (`make e2e`'s steps, 118 tests) passed against a stack built from the integration branch, with the fixes it needed; see [12-e2e-evidence](../12-e2e-evidence/README.md).
- **Breadcrumb switchers remain.** The breadcrumb still has its Agent and view switchers (now built from the same shared lists); 12-11 makes it plain.
- **Narrow tab row scrolls.** At 390 px the four tabs are wider than the column, so the row scrolls sideways inside itself (Conversations is partly behind the edge until scrolled); the page doesn't.
- **No pixel comparison** against the design canvas.
