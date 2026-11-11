# Evidence: ticket 11-12, signed-out pages, profile, security and status

Branch `ticket/11-12-signed-out-account-pages`, from `origin/candidate-reskin` at `61c67f3` (the merge of 11-04, #85). The claim commit `ee1800a` set Status `in-progress`. Then:

- `c27e349`: the signed-out pages, the invite page and the status page are a centred panel with the wave mark and no top bar. Form errors are `Notice`. The status page has a `Status` dot per dependency.
- `2cab434`: the shell's loading and error states use `Skeleton` and `Notice`; its empty states use `EmptyState`. Profile and Security are in the account menu and the section switcher.
- `3593d15`: Profile and Security restyled. The QR code and the recovery codes are on cards. Security loads with a `Skeleton`.
- `45bd503`: `docs/design/README.md`, `GLOSSARY.md` and the `studio-reskin` patterns describe what was built.
- `6d50173`: this folder's scripts.
- The last commit changes only this folder and the ticket file.

No backend code, route, API call or permission changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

**The signed-out frame** (`auth/AuthLayout.tsx`, `SignedOutFrame`) is a centred `surface.panel` on the canvas with the wave mark and "Studio" (`Brand`). It has no top bar: no `banner`, no breadcrumb. These pages use it:

- `AuthLayout`: sign in, sign up, two-factor sign-in, forgot password, reset password and every state of the invite page. The panel holds the mark, the title, the form and the footer line, with "System status" under it.
- The status page, wider, with the mark as a link home ("Studio home").
- The shell before the session is known: loading, could not reach the API, and a Member with no Organisation.

Inside the panel:

- Fields use `field.label` and `field.input`. The submit button is `button.primary`, full width.
- Links are accent and always underlined (`PANEL_LINK`), so they never rely on colour alone.
- **`FormError` becomes `Notice`.** Signed-out, Profile and Security pages use `ErrorNotice`, which renders `<Notice tone="error">` (an alert, as before) or nothing. The success messages (reset link sent, password reset) are `Notice tone="success"`. The wrong-account invite message keeps `role="alert"` with `notice.warning`. `FormError` stays exported as an alias of `ErrorNotice` for the pages that later tickets restyle, so their form errors look the same now.

**The status page** (`status/StatusPage.tsx`) is a `table` recipe with one row per dependency: API, Database, Redis and Worker. Each row's state is a `Status` dot with its word: OK (`ready`), Unavailable (`failed`) and Checking… (`working`). The summary line and the Worker's reply are unchanged.

**The shell's states** (`shell/SignedInShell.tsx`):

| State | Before | After |
| --- | --- | --- |
| Session loading | "Loading…" text | `Skeleton` "Loading the Studio" in the signed-out panel |
| API unreachable | alert text | `Notice tone="error"`, same words |
| No Organisation | status text | `EmptyState` with the same title and "Ask an Owner to invite you, then open the link in their email." |
| Organisation not found | heading and a sentence with a link | `EmptyState` with the same heading and sentence; "Go to your Organisation" is its primary button |

The invite page loads with a `Skeleton` ("Loading the invite"), and Security with a `Skeleton` ("Loading your security settings") on a card. Their errors are `Notice tone="error"`.

**Profile and Security** (`profile/ProfilePage.tsx`, `security/SecurityPage.tsx`):

- `PageHeader`, then a `surface.panel` card per form, with `text.subheading` titles and `button` recipes.
- The Require MFA notice is `Notice tone="warning"`.
- **MFA enrolment** shows the QR code and its fallback key on an inner card (a `figure` captioned by the key). The QR image sits on its own bordered tile; the API draws it on white, so it scans in either Appearance.
- **Recovery codes** are a grid of mono chips on their own card ("Save your recovery codes").

**Reaching Profile and Security:**

- The account menu holds **Profile, Security** and Sign out. Security is new here; the studio-reskin skill's R1 already listed it.
- The breadcrumb's section switcher offers **Profile** after Security, so both pages are reachable from the breadcrumb. On Profile the crumb is "Profile ▾", current, instead of a plain "Profile" crumb. While the Require MFA policy is waiting for enrolment, the switcher still offers only Security.

### Moved actions (behaviour otherwise unchanged)

| Before | After |
| --- | --- |
| Account menu: Profile, Sign out | Account menu: Profile, **Security**, Sign out |
| Section switcher: Projects, Cost (Owners), Settings, Security | Section switcher: Projects, Cost (Owners), Settings, Security, **Profile** |
| Profile page: plain "Profile" crumb | "Profile ▾" switcher crumb, current |
| Status page: header bar with a "RAG Agent Studio" link home (navigation "Main") | Signed-out panel whose wave mark is the link home ("Studio home"); no header bar |
| Signed-out pages: "RAG Agent Studio" text over the title | Wave mark and "Studio" |
| "Organisation not found": inline link "Go to your Organisation" | The same link as the empty state's button |

Words, routes, API calls, roles (`alert` for errors, `status` for progress and success) and permissions are unchanged.

## Test seams

The spec's frontend seam: `renderStudio` with MSW (the network seam). New or changed tests, each written red first:

- `shell/SignedInShell.test.tsx`: the account menu lists Profile, Security and Sign out, and opens both pages, each then the current section. The section switcher lists Profile and opens it. The loading state is the "Loading the Studio" skeleton. A Member with no Organisation sees the empty state. The status page has no top bar and its mark links home. 6 tests failed before the change.
- `auth/SignInPage.test.tsx`: each signed-out route (`/sign-in`, `/sign-up`, `/sign-in/mfa`, `/forgot-password`, `/reset-password`, `/accept-invite`) renders a `main` panel with an `h1` and the "Studio" mark, and no `banner` or breadcrumb.
- `security/SecurityPage.test.tsx`: the QR code and its key are on a card (a `figure`) inside the set-up card; the recovery codes are in the "Save your recovery codes" card; loading is a skeleton. 2 tests failed before the change.
- `invites/AcceptInvitePage.test.tsx`: loading is the "Loading the invite" skeleton.

Every existing alert, status and form test still passes unchanged, which shows the errors still announce as before. The seams were not confirmed with a human (none was available), so the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | Signed-out pages are a centred panel with the wave mark and no top bar; `FormError` becomes `Notice` | `SignedOutFrame` and `AuthLayout`. The test "%s is a centred panel with the Studio mark and no top bar" covers 6 routes. [shots-axe.log](shots-axe.log) records "top bar no" for all 17 signed-out views. `ErrorNotice`/`FormError` render `Notice tone="error"`. Screenshots `sign-in*`, `sign-up`, `mfa-challenge`, `forgot-password*`, `reset-password*`, `accept-invite-*`. |
| 2 | Profile and Security are reachable from the account menu and the breadcrumb; MFA enrolment shows the QR code and recovery codes on cards | Tests: "the account menu opens the Profile and Security…", "the breadcrumb's section switcher reaches the Profile", and the Security page's enrolment test. Screenshots `menu-account`, `menu-sections-on-profile`, `security-enrol`, `security-recovery-codes`. |
| 3 | The status page uses `Status` dots for each dependency | `StatusRow` renders `<Status tone>`. Screenshots `status` and `status-degraded`. |
| 4 | Shell loading and error states use `Skeleton` and `Notice` | `SignedInShell`: `Skeleton` "Loading the Studio" and `Notice tone="error"`. Tests "shows a loading state while the session is checked" and "says when the API cannot be reached". Screenshots `shell-loading`, `shell-error`, `no-organisation`, `organisation-not-found`. |
| 5 | Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR | The moved-actions table is above and in the PR. All 948 tests pass. |
| 6 | The palette ratchet baseline is lowered to the new count | The new count is **24**, the same as before: these pages had no palette classes left after 11-03, and the new code uses tokens and recipes only. The baseline equals the count (`24 palette-class uses under apps/studio/src (baseline 24).`, [frontend-tests.log](frontend-tests.log)). |
| 7 | Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas | [screenshots/](screenshots/) has 78 images: 26 views, each `-light`, `-dark` (system) and `-chosen-dark`. They follow `docs/design/README.md` (*Pages*: signed-out pages are a centred `surface.panel` with the wave mark, no top bar; settings and forms are a panel per group). |
| 8 | axe reports zero AA violations on the changed pages in both Appearances | [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` and `wcag22aa`, on 26 views × 3 Appearances, **0 violations**. |
| 9 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams are above. `make test-frontend`: 74 files, **948 tests**, 100% statements (4340/4340), branches (2997/2997), functions (1552/1552) and lines (3826/3826). |
| 10 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | No new domain term. **Breadcrumb** now says Profile, Security and Sign out are in the account menu. No ADR decision changed. |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `6d50173`, which is `origin/candidate-reskin` (`61c67f3`) plus this branch. Each log's first line names its command and commit. GitHub Actions is down, so these are local.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 74 files, 948 tests, 100%. `embed.js` is 778 B gzipped. 24 palette-class uses (baseline 24). | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Screenshots and axe | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 78 screenshots, 0 axe violations. | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack.** There is no Docker daemon in this sandbox, so the backend and the Playwright specs against the stack (`smoke`, `mfa`, `password-reset`, `invites` and others touching these pages) were not run. They type-check and lint. Their selectors (headings, `row` names, `status` and `alert` text, `openSection(…, "Account", "Profile")`) are unchanged. [shots.test.ts](shots.test.ts) stands in for the axe run: it serves the built Studio, answers the API with the unit tests' MSW fakes, and runs the same axe tags. No backend code changed.
- **The QR code in the screenshots is a stand-in.** The unit tests' fake is an empty SVG, so the shots draw a non-scannable pattern in segno's style (black on white). The real one comes from the API, also on white.
- **Concurrency.** 11-05 and 11-11 are open at the same time. This branch leaves their pages alone: their `FormError` imports keep working, and the `TAB_ROWS` helpers are untouched.
- **No pixel comparison.** The design canvas could not be opened from this sandbox. The comparison is against `docs/design/README.md` and the patterns.
