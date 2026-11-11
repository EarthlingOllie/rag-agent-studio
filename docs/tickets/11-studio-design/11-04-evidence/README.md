# Evidence: ticket 11-04, shell, breadcrumb and navigation test helpers

Branch `ticket/11-04-shell-navigation`, from `origin/candidate-reskin` at `cd01dbe` (the merge of 11-03, #84). The claim commit `44ebf4f` set Status `in-progress`. Then:

- `023ac8b` adds the navigation helpers, for Testing Library and Playwright, and a Playwright harness spec for the Playwright one.
- `7d0591f` is the shell: one top bar with the breadcrumb, the Appearance toggle and the account menu. The side menu is gone. It also rewrites the shell's own tests.
- `3899984` moves every other navigation step in the unit and end-to-end tests to the helpers.
- `06c9d45` adds **Breadcrumb** to `GLOSSARY.md` and updates `docs/design/README.md` and the `studio-reskin` patterns.
- `7d7f781`, `c95e987` and `a0293bb` are this folder's scripts. `0da9635` fixes the account button's name after axe flagged it (below).
- The last commit changes only this folder and the ticket file.

No backend code, route, API call or permission changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

**The top bar** (`shell/SignedInShell.tsx`, `OrganisationShell`) is the design system's `TopBar`, with these parts:

- The wave mark and "Studio", a link to `/` named "Studio home".
- The breadcrumb.
- The Appearance toggle.
- The account menu.

The page sits in `layout.page` below it. The old header (product name, Member name, Profile link, Sign out button) and the side menu (`navigation "Organisation"`) are gone.

**The breadcrumb** (`shell/StudioBreadcrumb.tsx`) is computed from the route with `useMatchRoute`. Pages register nothing.

| Where you are | Breadcrumb (current crumb in bold) |
| --- | --- |
| Projects list | `Analytical Engines / **Projects ▾**` |
| A Project (any section, until 11-05) | `Analytical Engines / Projects ▾ / **HR handbook**` |
| Cost (Owner), Settings, Security | `Analytical Engines / **Cost ▾**`, `**Settings ▾**`, `**Security ▾**` |
| Profile, or Cost for an Editor | `Analytical Engines / **Profile**`, `**Cost**` (plain crumbs: these are not in the menu) |
| An Organisation the Member doesn't belong to | the Organisation switcher only, labelled "Choose an Organisation" |

- **Organisation crumb** (`shell/OrganisationSwitcher.tsx`, `OrganisationCrumb`). A Member of several Organisations gets a switcher, "<name>, Organisations", that lists them with the open one current. Choosing another calls the same `useSwitchOrganisation` mutation as before, then opens its Projects. Today's error handling is kept: the "Couldn't switch Organisation. Try again." alert, and the switcher disabled while a switch is under way (`Menu` and `CrumbSwitcher` gain a `disabled` prop). Choosing the open Organisation does nothing, as re-selecting it in the old `<select>` did. A Member of one Organisation sees its name as plain text, as before. It is not a link: a router `<Link>` to the page you are on always gets `aria-current="page"`, and only the last crumb may have that.
- **Section switcher**, "<section>, Organisation sections". It offers Projects, Cost (Owners only, as the side menu had it), Settings and Security, each with an icon. While the Organisation requires MFA and the Member has none, it offers only Security (the existing `mustEnrol` rule; the redirect to Security is unchanged). Every item is a router link (`renderLink`) with a real `href`.
- **Current crumb**: the last crumb is in the accent colour with `aria-current="page"` (`crumbClass(true)`). Ancestor crumbs are muted and have no `aria-current`.
- **Switcher names**: "<label>, <what it holds>": "Analytical Engines, Organisations" and "Projects, Organisation sections".

**The account menu** (`shell/AccountMenu.tsx`) is the Member's initials. Its button is named "<Member>, Account", for example "Ada Lovelace, Account", so the Member's name is still in the top bar for screen readers. It holds:

- **Profile**: a router link, shown while the Organisation exists.
- **Sign out**: the existing `useSignOut` flow. It keeps the "Sign-out failed. Try again." alert, and is disabled while signing out.

axe's `label-content-name-mismatch` flagged the first version, which set `aria-label` over the visible initials. The name is now visually hidden text, and the avatar is `aria-hidden` (`0da9635`).

### Moved actions (behaviour otherwise unchanged)

| Before | After |
| --- | --- |
| Side menu links: Projects, Cost (Owners), Organisation settings, Security | Section switcher items: Projects, Cost (Owners), **Settings**, Security. The page is still headed "Organisation settings". |
| Header Organisation `<select>` (combobox "Organisation") | Organisation crumb switcher (button "<name>, Organisations", menu "Organisations") |
| Header Profile link | Account menu → Profile |
| Header Sign out button | Account menu → Sign out |
| Member's name as header text | The account button's name ("<Member>, Account") |
| "RAG Agent Studio" header text | Wave mark and "Studio", linking home |

Unchanged on purpose: the status page's own "RAG Agent Studio" header, which is for 11-12. The Project tab row and the Organisation settings tab row are for 11-05 and 11-11.

## Navigation test helpers

Both have the same vocabulary. The menus are `"Organisations" | "Organisation sections" | "Project sections" | "Organisation settings" | "Account"`.

- `apps/studio/src/test/navigation.ts` (Testing Library): `openSection(menu, item)`, `sectionNames(menu)`, `currentSection(menu)`, `hasMenu(menu)` and `menuButton(menu)`.
- `e2e/fixtures/navigation.ts` (Playwright): `openSection(page, menu, item)`, `sectionNames(page, menu)` and `menuButton(page, menu)`.

`openSection` opens the switcher whose button ends ", <menu>" and follows the `menuitem`. `sectionNames` lists a menu's items, then closes it.

Two menus are still tab rows: "Project sections" (navigation "Project") and "Organisation settings". Both helpers list them in a `TAB_ROWS` map. The slice that turns a row into a switcher (11-05, 11-11) deletes its entry, and no test changes.

**Migration:**

| Suite | Calls to the helpers | Files |
| --- | --- | --- |
| Unit | 45 | 14 |
| End-to-end | 122 | 38 |

No test reaches a section through a navigation landmark any more. The one remaining `navigation "Organisation"` query asserts that the side menu is gone. Two unscoped `getByRole("list")` queries are scoped to `main`, because the breadcrumb is an `<ol>`.

**Role-based hiding** is now an item missing from `sectionNames`:

- Cost for an Editor (`CostPage.test.tsx`).
- Members and Audit for an Editor (`AuditPage`, `MembersPage` and `MembersList` tests; `members`, `invites` and `organisation-switcher` specs).
- Everything but Security while enrolment is required (`RequireMfa.test.tsx`, `require-mfa.spec.ts`).

**Candidate merge:** `origin/candidate` (`d79dd3f`, #81) was already in `candidate-reskin`. It was checked again right before the PR: `git log HEAD..origin/candidate` is empty. Every feature's navigation tests are therefore migrated. No other design ticket is open.

## Test seams

The spec's frontend seams:

- **Network seam:** `renderStudio` with MSW. `shell/SignedInShell.test.tsx` covers:
  - the top bar's parts and the absence of the side menu;
  - the section switcher's items, `href`s and current item;
  - the breadcrumb following the route and moving `aria-current`, including the Project crumb and a Project that fails to load;
  - the account menu: Profile, sign-out, sign-out failure and the disabled item while signing out;
  - the not-found Organisation.

  `shell/OrganisationSwitcher.test.tsx` covers switching, remembering, failure, disabled-while-switching, choosing an Organisation from a not-found one, and re-choosing the open one. Each test was written red first, against the old shell (19 failing), then made green.
- **End-to-end seam:** the Playwright helper has its own harness spec, `e2e/harness/navigation.spec.ts`. It covers a switcher and a remaining tab row, for both `openSection` and `sectionNames`, in Chrome.

The seams were not confirmed with a human (none was available), so the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | `OrganisationShell` renders `TopBar` with the mark, the breadcrumb, the Appearance toggle and the account menu; the side menu is gone | `SignedInShell.tsx`. Test: "one top bar holds the mark, the breadcrumb, the Appearance toggle and the account menu; there is no side menu". Screenshots below. |
| 2 | The Organisation crumb switches Organisation (with today's error handling); the org-level section switcher offers Projects, Settings and Security, and only Security while MFA enrolment is required | `OrganisationSwitcher.test.tsx` (10 tests, including the failure alert and the disabled switcher). `SignedInShell.test.tsx` expects `["Projects", "Cost", "Settings", "Security"]` for an Owner. Cost is kept for Owners because it was in the side menu, so behaviour is unchanged. `RequireMfa.test.tsx` expects `["Security"]`. |
| 3 | The breadcrumb is computed from the route; the current crumb is in the accent colour with `aria-current="page"`, and each switcher's name is "<label>, <what it holds>" | `StudioBreadcrumb.tsx` uses `useMatchRoute`. Test: "the breadcrumb follows the route and marks the current page". `crumbClass(true)` is `text-accent` (screenshots). Names: "Projects, Organisation sections", "Analytical Engines, Organisations", "Ada Lovelace, Account". |
| 4 | Switcher items that navigate are router links | Section items and Profile use `renderLink` with `<Link>`. The test asserts `href` `/organisations/<id>/settings`. Organisation switching is an API action followed by navigation, as before, so those items are buttons. |
| 5 | `openSection` helpers exist for Playwright (`e2e/fixtures/navigation.ts`) and Testing Library (`apps/studio/src/test/navigation.ts`), and every navigation step in unit and end-to-end tests uses them | Both files exist. Migration counts are above. [e2e-harness.log](e2e-harness.log) shows 14 harness tests passing, 4 of them for the helpers. |
| 6 | Role-based hiding is asserted as a missing menu item | `sectionNames(...)` with `not.toContain(...)`. The list is above. |
| 7 | The latest `candidate` is merged into this ticket's branch immediately before landing, so navigation tests for every feature are migrated; no other design ticket is open while this one is | `origin/candidate` has nothing that `candidate-reskin` lacks (checked at PR time). No other 11-xx PR is open. |
| 8 | Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR | The moved-actions table is above and in the PR. No routes, API calls or permissions changed. All 941 Studio tests pass. |
| 9 | The palette ratchet baseline is lowered to the new count | The new count is **24**, the same as before: the shell had no palette classes left after 11-03, and the new files use tokens only. The baseline equals the count (`24 palette-class uses under apps/studio/src (baseline 24).`, [frontend-tests.log](frontend-tests.log)). The 24 are the 11-03 list, for 11-06, 11-10 and 11-13. |
| 10 | Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas | [screenshots/](screenshots/) has 66 images: all 19 signed-in pages, plus the section, account and Organisation menus open, each `-light`, `-dark` (system) and `-chosen-dark`. The top bar follows the canvas's *Direction* page: mark, `Org / Section ▾ / item` with the current crumb in accent, and the toggle and avatar on the right. Signed-out pages have no top bar and did not change. |
| 11 | axe reports zero AA violations on the changed pages in both Appearances | [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` and `wcag22aa`, on 22 views × 3 Appearances, **0 violations**. |
| 12 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams are above. `make test-frontend`: 74 files, **941 tests**, 100% statements (4338/4338), branches (2987/2987), functions (1552/1552) and lines (3819/3819). |
| 13 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | **Breadcrumb** added, and **Active Organisation** now points at it. No decision changed: ADR-0013 already says navigation is the breadcrumb. |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `a0293bb`, which is `origin/candidate-reskin` (`cd01dbe`) plus this branch. Each log's first line names its command and commit. GitHub Actions is down, so these are local.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 74 files, 941 tests, 100%. `embed.js` is 778 B gzipped. 24 palette-class uses (baseline 24). | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` (Chrome) | exit 0, 14 passed | [e2e-harness.log](e2e-harness.log) |
| Screenshots and axe | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 66 screenshots, 0 axe violations. | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack.** There is no Docker daemon in this sandbox, so the backend, the 38 migrated Playwright specs and `e2e/harness/axe.spec.ts` against the stack were not run. The specs type-check and lint. The helper they call is checked by the harness spec in Chrome. [shots.test.ts](shots.test.ts) stands in for the axe run: it serves the built Studio, answers the API with the unit tests' MSW fakes, and runs the same axe tags. No backend code changed.
- **Project crumb is plain text until 11-05**, which makes it a Project switcher and adds the "Project sections" switcher in place of the tab row.
- **Narrow screens.** The top bar wraps, from `TopBar`'s `flex-wrap`. Collapsing the middle crumbs is 11-13.
- **No pixel comparison.** The design canvas could not be opened from this sandbox. The comparison is against `docs/design/README.md` and the patterns.
