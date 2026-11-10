# Evidence: ticket 12-08, Sidebar navigation on desktop

Branch `t/12-08`, from `origin/candidate-reskin` at `63a7569` (Split spec 12 into eleven tickets). The claim commit `4f52e51` set Status `in-progress`. Then:

- `2bdda60` adds the sidebar, teaches the navigation helpers (Playwright and Testing Library) to follow it, moves the end-to-end specs to it, adds `e2e/tests/sidebar.spec.ts` and the **Sidebar** glossary entry.
- `22cc0c8` adds this folder's first run (logs, screenshots) and sets Status done.
- `cfab1d5`: run against the compose stack, the new sidebar spec waited for an `h1` naming the Agent, but the Agent page keeps the Project as its `h1` and names the Agent at level 2; the spec now looks for that. It also rewords the **Breadcrumb** glossary entry to say the switcher menus stay.
- The last commit changes only this folder (the stack end-to-end run).

No backend code, API call, route or permission changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

**The sidebar** (`shell/StudioSidebar.tsx`, built from `design/Sidebar.tsx`). A navigation landmark named "Studio", computed from the route and the Member's session; pages register nothing. From the top: the Organisation switcher (`shell/OrganisationSwitcher.tsx`; the Organisation's name as plain text for a Member of one), the list "Organisation sections" (Projects, Cost for Owners only, Settings), and inside a Project a rule, the Project switcher (the open Projects, then All Projects; `shell/projectNavigation.tsx`, shared with the breadcrumb) and the list "Project sections" (Documents, Instructions, Agents, Conversations, Analytics, Settings).

**Current link.** The current link carries `aria-current="page"`, and the `sidebarLink` recipe styles that state with the soft accent fill (`bg-accent-soft`, `text-accent-ink`). Documents is current on the Project page and the Document viewer; Agents on every Agent page and view; Conversations on a Conversation; Settings (Organisation) on every settings page. The router's own prefix matching is turned off (`exact`), so Projects is not current inside a Project.

**Require MFA.** Until the Member enrols, the Organisation list holds only Security (current) and no Project navigation is shown; the shell still redirects every other page to Security.

**Layout** (`shell/SignedInShell.tsx`). Below the top bar, a `md:flex` row: the sidebar (`w-60`, 240 px, sticky at the top, full height, scrolling on its own) and `main`, which keeps `layout.page` (1160 px maximum, centred) in the space beside it. Below `md` the sidebar is hidden (the drawer is 12-09) and the breadcrumb's switchers, unchanged, reach every page.

**Navigation helpers** (`apps/studio/src/test/navigation.ts`, `e2e/fixtures/navigation.ts`). `openSection`, `sectionNames` and `currentSection` keep their names and menu vocabulary: "Organisation sections" and "Project sections" now read the sidebar's lists, "Organisations" and "Projects" its switchers; the other menus stay in the top bar. A `sidebar(page)` locator is added. Specs that reached Security or Profile through the old Organisation sections menu now use the Account menu (`auth`, `invites`, `mfa`, `require-mfa` specs; `SignUpPage`, `AcceptInvitePage`, `SecurityPage`, `AgentViews` tests).

### Moved actions (behaviour otherwise unchanged)

| Before | After |
| --- | --- |
| Projects, Cost and Settings were reached from the breadcrumb's Organisation sections menu | They are links in the sidebar (the breadcrumb menu remains until 12-11) |
| A Project's sections and the Project switcher were breadcrumb menus | They are in the sidebar under the Project switcher (the breadcrumb menus remain) |
| The Organisation switcher was the first crumb | It is at the top of the sidebar (and still the first crumb) |

## Test seams

- **Network seam** (`renderStudio` with MSW): `shell/Sidebar.test.tsx` (new, 14 tests and a 5-case table) covers the landmark and its order, following links, Settings current on its inner pages, Cost for Owners only, Profile and Security from the account menu, the Organisation switcher for a Member of two, the Project switcher and six sections, inner pages keeping their section current, archived and missing Projects, Require MFA offering only Security, an unknown Organisation, and `main` beside the sidebar. `SignedInShell.test.tsx` and `OrganisationSwitcher.test.tsx` keep the breadcrumb switcher behaviour green. CSS width and the accent fill can't be measured in jsdom: [shots-axe.log](shots-axe.log) records them in Chrome.
- **End-to-end seam:** `e2e/tests/sidebar.spec.ts` (an Owner's journey with axe, and the 1160/240 px layout at 1440 px). The `harness` project (`e2e/harness/navigation.spec.ts` drives the rewritten helpers) passes ([e2e-harness.log](e2e-harness.log)). Against the compose stack the new and moved specs pass, 14 of 14 ([e2e-stack-changed.log](e2e-stack-changed.log)), and the whole `studio` project has no failure this ticket introduces ([e2e-stack-full.log](e2e-stack-full.log), [e2e-stack-base.log](e2e-stack-base.log); see Results).

The seams were not confirmed with a human (none was available), so the spec's shared test seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | The shared navigation helpers learn to follow sidebar links, keeping names and menu vocabulary | `apps/studio/src/test/navigation.ts`, `e2e/fixtures/navigation.ts`; `e2e/harness/navigation.spec.ts` passes ([e2e-harness.log](e2e-harness.log), 14 passed); every Studio test passes ([frontend-tests.log](frontend-tests.log)). |
| 2 | The sidebar is a navigation landmark named "Studio": Organisation switcher (plain text for one Organisation), Projects, Cost (Owners), Settings | `Sidebar.test.tsx` first five tests and the switcher test; [shots-axe.log](shots-axe.log) `links [Projects, Cost, Settings]` on every wide line, `switchers [- | …]` for one Organisation and `[Analytical Engines, Organisations | …]` on `two-organisations`. |
| 3 | Inside a Project: the Project switcher (open Projects, then All Projects) and its six sections | `Sidebar.test.tsx` "inside a Project…" and "the sidebar's Project switcher…"; shots-axe.log project pages list `[Documents, Instructions, Agents, Conversations, Analytics, Settings]`; screenshots `documents-*.png` etc. |
| 4 | The current link has the soft accent fill and `aria-current="page"`, and stays current on inner pages | `sidebarLink` recipe (`aria-[current=page]:bg-accent-soft`); `Sidebar.test.tsx` "a section stays current on its inner pages" (Document viewer, Agent, Agent view, Conversation, Project Settings); shots-axe.log marks the current link with `*` (`document-viewer` → `Documents*`, `agent-*` → `Agents*`, `conversation` → `Conversations*`); screenshots show the fill. |
| 5 | Under Require MFA the sidebar offers only Security until the Member enrols | `Sidebar.test.tsx` "under the Require MFA policy…"; shots-axe.log `require-mfa-enrol` → `links [Security*]`; `require-mfa-enrol-*.png`. |
| 6 | Main content keeps its 1160 px maximum, centred beside a fixed sidebar of about 240 px | shots-axe.log at 1440 px: `sidebar 240px; main 1160px at 260, 20px right` (20 px each side of the 1200 px beside the sidebar) on every wide page; `e2e/tests/sidebar.spec.ts` second test; `Sidebar.test.tsx` "the main content sits beside the sidebar". |
| 7 | The breadcrumb's switcher menus still work; the end-to-end specs move to the sidebar and stay green | `SignedInShell.test.tsx` and `OrganisationSwitcher.test.tsx` breadcrumb switcher tests pass; shots-axe.log narrow lines (sidebar hidden) still list the breadcrumb switchers; against the compose stack the moved specs (`auth`, `invites`, `mfa`, `require-mfa`), `organisation-switcher` (the breadcrumb's Organisation switcher) and the new `sidebar` spec pass, 14 of 14 ([e2e-stack-changed.log](e2e-stack-changed.log)); harness green. Every spec that uses the navigation helpers and fails in the full run fails the same way at `63a7569`, before this ticket ([e2e-stack-base.log](e2e-stack-base.log)). |
| 8 | Design system only; palette ratchet passes | `design/Sidebar.tsx` uses token utilities only (`bg-surface`, `border-line`, `text-ink-2`, `bg-accent-soft`…), no palette classes or `dark:`; [frontend-tests.log](frontend-tests.log) ends "0 palette-class uses under apps/studio/src (none allowed)." |
| 9 | Light and dark screenshots, wide (1440) and narrow (390), and the axe sweep in both Appearances | [screenshots/](screenshots/): 25 page views (the 23 signed-in pages, Require MFA enrolment, a Member of two Organisations) × `-light`, `-dark`, `-narrow-light`, `-narrow-dark` = 100 files. [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`, **0 violations and 0 overflows** on all 100 views. |
| 10 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage | Seams above; [frontend-tests.log](frontend-tests.log): 80 files, 1055 tests, 100% statements (4594/4594), branches (3251/3251), functions (1661/1661), lines (4020/4020). |
| 11 | New domain terms in `GLOSSARY.md`; ADRs updated if a decision changed | **Sidebar** added; **Breadcrumb**, **Project section** and **Active Organisation** updated. No decision changed beyond draft ADR-0014, which 12-11 moves into `docs/adr/` (its own criterion). |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `2bdda60` (the implementation commit; this commit adds only evidence and the ticket). Each log's first line names its command and commit.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint `--max-warnings=0`, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 80 files, **1055 tests**, 100% statements, branches, functions and lines. `embed.js` 0.77 kB gzipped. 0 palette-class uses. | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0, 2394 links resolve | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` | exit 0, 14 passed | [e2e-harness.log](e2e-harness.log) |
| Changed stack specs parse | `playwright test --project=studio --list …` | exit 0, 14 tests in 6 files | [e2e-list.log](e2e-list.log) |
| Stack: changed specs | [run-stack-e2e.sh](run-stack-e2e.sh): `playwright test --project=studio` sidebar, organisation-switcher, require-mfa, mfa, auth, invites | exit 0, **14 passed** | [e2e-stack-changed.log](e2e-stack-changed.log) |
| Stack: whole `studio` project | `playwright test --project=studio` | 82 passed, 13 failed (see below) | [e2e-stack-full.log](e2e-stack-full.log) |
| Stack: the failing specs before this ticket | the same specs, from `63a7569`'s frontend, against a Studio image built from it | 12 of the 13 fail the same way there (5 passed, 12 failed) | [e2e-stack-base.log](e2e-stack-base.log) |
| Stack: the 13th failure again | `playwright test --project=studio --repeat-each=3 e2e/tests/credentials.spec.ts` | exit 0, 6 passed | [e2e-stack-credentials-rerun.log](e2e-stack-credentials-rerun.log) |

**The stack run.** [run-stack-e2e.sh](run-stack-e2e.sh) builds the images from [stack/](stack/) (the repository's Dockerfiles plus the sandbox proxy's CA and without the `apt-get upgrade` step, since the proxy refuses plain-HTTP apt), with the light backend (`WITH_PDF=false`, `BUNDLE_MODELS=false`), starts the stack with [stack/env-override.yml](stack/env-override.yml) (the fake embedder and heuristic classifiers the compose file's comments name for that build; Postgres and Redis unpublished, as the sandbox's own hold 5432 and 6379), seeds the demo and runs the suite. In the recorded run Docker Hub answered the build's metadata request with 429 Too Many Requests ([stack-up.log](stack-up.log)), so the stack kept running the images built earlier in the session from the same tree: no frontend, backend or seed file differs between `2bdda60` and this commit (`git diff --stat 2bdda60 HEAD -- frontend backend seed` lists only `e2e/tests/sidebar.spec.ts`). The base comparison image did build.

**The 13 failures.** None comes from this ticket:
- 12 fail identically at `63a7569`, before it ([e2e-stack-base.log](e2e-stack-base.log)). Two follow from the light backend: `documents` (line 68) and `playground` expect the bundled ONNX classifier's wording and get the heuristic one's. The rest are `candidate-reskin` specs still written for the pre-reskin pages (for example `projects` finds two level-2 headings matching "Documents", `accessibility` finds the Project's `h1` and the handbook's own `h1` on the Document viewer, `version-kpis` reads the Agent filter as an input), which the later spec-12 tickets own.
- `credentials` timed out once waiting for the "was deleted" toast; it passed in the session's first full run and three times in a row after ([e2e-stack-credentials-rerun.log](e2e-stack-credentials-rerun.log)).
| Screenshots, axe, overflow, sidebar measurements | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 100 page views, 0 axe violations, 0 overflows | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **Light stack.** The stack ran without PDF support or the bundled models (see Results), so the two specs that check the ONNX classifier's wording can't pass here; they fail the same way before this ticket. The spec-12 run in [12-e2e-evidence](../12-e2e-evidence/README.md) used the bundled models, and both pass there. The backend's own tests were not run: this ticket changes no backend code.
- **Pre-existing stack failures.** 12 `studio` specs fail on `candidate-reskin` at `63a7569` too (see Results); fixing them is outside this ticket. **Closed after spec 12 merged:** the whole compose-stack suite (`make e2e`'s steps, 118 tests) passed against a stack built from the integration branch, with the fixes it needed; see [12-e2e-evidence](../12-e2e-evidence/README.md).
- **Narrow screens** hide the sidebar; the drawer is ticket 12-09. The narrow screenshots show the breadcrumb navigation that remains.
- **No pixel comparison** against the design canvas; the layout follows the spec and `docs/design/README.md`.
