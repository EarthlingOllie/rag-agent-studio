# Evidence: ticket 11-11, Organisation settings

Branch `ticket/11-11-organisation-settings`, from `origin/candidate-reskin` at `61c67f3` (the merge of 11-04, #85). The claim commit `c744717` set Status `in-progress`. Then:

- `b7daf99` is the Settings switcher crumb. It replaces the tab row. It also puts the page header and General's panels in place, and removes "Organisation settings" from both navigation helpers' `TAB_ROWS`.
- `8dafb8b` moves Members, Credentials, Models (the Default Model and the price table), Theme (the form only) and Audit onto the design system.
- `91c6160` updates `GLOSSARY.md` (**Breadcrumb**), `docs/design/README.md` and the `studio-reskin` patterns.
- `5f236f6` holds this folder's scripts.
- The last commit changes only this folder and the ticket file.

No backend code, route, API call or permission changes. `frontend/packages/ui` is untouched.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

**The Settings switcher crumb** (`shell/SettingsCrumb.tsx`) appears on every Organisation settings page. The breadcrumb reads `Analytical Engines / Settings ▾ / **Members ▾**`.

- "Settings ▾" (the Organisation's section switcher) is now an ancestor: it is muted and has no `aria-current`.
- The last crumb is the area the Member is in, in accent with `aria-current="page"`. It is named "<area>, Organisation settings".
- The crumb's menu lists General, Credentials, Models and Theme, then Members and Audit for Owners only, which is the tabs' order and visibility. Each item has an icon and is a router link. The current area is marked.
- On an address under settings that is not an area, the crumb reads "Not found" and still offers every area.
- New line icons: `key`, `model`, `palette`, `members`.

**The page** keeps one `PageHeader`, "Organisation settings", with a one-line description. The tab row is gone. The page is wrapped in a `ToastProvider`. It is scoped to settings for now, so its always-present live region doesn't sit beside other pages' own status messages. `docs/design/README.md` says to move it up when another section needs toasts.

| Area | Now |
| --- | --- |
| General | Three `surface.panel`s: Two-factor authentication, Retention (Save is the panel's primary), and Leave this Organisation (`button.danger`, then a destructive `ConfirmDialog`, "Yes, leave <Organisation>") |
| Members | The Members `table.wrap` card. The role `<select>` change is confirmed by a toast ("Grace Hopper is now an Owner."). Remove opens a destructive `ConfirmDialog`, "Remove Grace Hopper?", and the removal is confirmed by a toast. The invite form is a panel with labels above its fields and Invite as its one primary button. An invite is confirmed by a toast ("Invited lin@example.test."), and its link stays on the page in a "New invite" panel to copy. The pending invites are a table card. New link and Revoke are confirmed by toasts. |
| Credentials | A table card. The check result is a `Badge`: **Working** (`checkPassed`) or **Check failed** (`checkFailed`) with the reason beside it. Delete opens a destructive `ConfirmDialog`, "Delete <name>?", whose confirm button is "Yes, delete <name>". The Add a credential form is a panel with labels above, with "Check and save" as its primary. The AWS role setup is a sunken inset inside it. |
| Models | The Default Model is a panel. "Save Default Model" is its primary, and the save is confirmed by a toast. The price table is a table card with `Pagination`, ten models to a page ("Prices for <credential> pages"). An override form is a panel, and a saved override is confirmed by a toast. |
| Theme | The form's groups (Colours, Shape and type, Mode and launcher, Logo and avatar) are panels. Inputs and selects use the field recipes, and "Save Theme" is the primary. The contrast warning is `notice.warning` and "Theme saved" is `notice.success`. **`WidgetPreview` is byte-for-byte unchanged**: `diff` of the function against `61c67f3` is empty. |
| Audit | The filters are a toolbar of labelled selects and dates. The log is a table card. Below it, "Page X of Y · N events" sits beside `Pagination` ("Audit Events pages"), which replaces the Previous/Next pager. Previous and Next keep their names. |

### Moved actions (behaviour otherwise unchanged)

| Before | After |
| --- | --- |
| Settings tab row: General, Credentials, Models, Theme, Members, Audit (the last two for Owners) | Settings switcher crumb, same items and visibility (menu "Organisation settings") |
| Remove a Member: inline "Yes, remove X / Cancel" in the row | `ConfirmDialog` "Remove X?" with the same "Yes, remove X" button |
| Leave the Organisation: inline "Yes, leave X / Cancel" | `ConfirmDialog` "Leave X?" with the same "Yes, leave X" button |
| Delete a credential: inline "Yes, delete X / Cancel" | `ConfirmDialog` "Delete X?" with the same "Yes, delete X" button |
| Member role change and removal messages: inline text | Toasts, with the same words |
| Invite result: one status box with the message and link | Toast "Invited <email>." / "New invite link for <email>.", plus the "New invite" panel with the same message, link, Copy link and expiry |
| Revoking an invite: no message | Toast "Revoked the invite for <email>." |
| Default Model and price override saved: inline status | Toasts, with the same words |
| Credential status: "Working" / "Check failed: <reason>" text | `Badge` Working / Check failed, with the reason beside it |
| Audit pager: Previous page · "Page X of Y" · Next page | "Page X of Y · N events", then `Pagination` (Previous, page numbers, Next) |
| Models: link "Add one on the Credentials tab" | "Add one in Credentials" (there are no tabs) |

## Test seams

The spec's frontend seams:

- **Network seam:** `renderStudio` with MSW.
  - `shell/SignedInShell.test.tsx` has three new tests:
    - "Organisation settings are a Settings switcher crumb…" checks the items, the `href`s, the current marks, following an item, and the Settings section crumb no longer being current.
    - "an Editor's Settings crumb leaves out Members and Audit".
    - "an unknown settings address says so in the Settings crumb…".
  - These were written red first, against the tab row (2 failing), then made green.
  - The page tests changed to the new behaviour, red first where behaviour changed:
    - `MembersList`: the confirmation dialog and the toasts.
    - `MembersPage`: the invite toast, the "New invite" region, and the revoke and new-link toasts.
    - `CredentialsPage`: the Badge words and colour, and the delete dialog.
    - `PriceTable`: two new paging tests and the toasts.
    - `AuditPage`: the `Pagination` landmark and page buttons.
    - `ModelsPage`: the toast, and a new saving-state test.
    - `Badge`: the two new kinds.
- **End-to-end seam:** the Playwright helper's "Organisation settings" entry is removed from `TAB_ROWS`, so all 46 `openSection`/`sectionNames` calls for that menu (unit and e2e) now open the switcher. No spec changed for that. Two specs changed for renamed things:
  - `invites.spec.ts` reads the invite message from the "New invite" region.
  - `models.spec.ts` follows "Add one in Credentials".

  [e2e-harness.log](e2e-harness.log): 14 harness tests pass in Chrome.

The seams were not confirmed with a human (none was available), so the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | The Settings crumb lists General, Credentials, Models, Theme, and Members and Audit for Owners only | `SettingsCrumb.tsx`. Owner: `["General", "Credentials", "Models", "Theme", "Members", "Audit"]`. Editor: `["General", "Credentials", "Models", "Theme"]` (`SignedInShell.test.tsx`; also `MembersPage`, `MembersList` and `AuditPage` tests). Screenshots `menu-settings-*` and `menu-settings-editor-*`. |
| 2 | Forms sit in panels with labels above fields and one primary per form; the price table and audit log use table cards with `Pagination` | `surface.panel` and `field.label` above `field.*` in every form; one `button.primary` per form (Retention Save, Invite, Check and save, Check and rotate, Save Default Model, Save prices, Save Theme). The MFA toggle is a secondary action button, and Leave is `button.danger`. Price table and Audit log: `table.wrap` with `Pagination` (tests "a long price table is paged…", "Owners page through long histories…"). |
| 3 | Credentials show checks with `Badge` and deletes with `ConfirmDialog`; invites and member changes confirm with `Toast` | `CheckResult` uses `Badge` `checkPassed`/`checkFailed`. The delete is a destructive `ConfirmDialog` (test "an Owner deletes an unused credential after confirming"). `useToast().show(...)` for invite, new link, revoke, role change and removal (MembersPage and MembersList tests). Screenshots `dialog-delete-credential-*`, `dialog-remove-member-*`, `toast-role-changed-*`, `invite-issued-*`. |
| 4 | The Theme editor's form is reskinned; the widget preview (`packages/ui`) is untouched | Theme form on panels and recipes. `git diff 61c67f3 -- frontend/packages` is empty. `WidgetPreview` is identical to `61c67f3`. Screenshots `settings-theme-*`. |
| 5 | Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR | The moved-actions table is above and in the PR. No routes, API calls or permissions changed. All 949 Studio tests pass. |
| 6 | The palette ratchet baseline is lowered to the new count | The new count is **24**, the same as before. `src/settings` had no palette classes left after 11-03, and the new code uses tokens only. The baseline equals the count (`24 palette-class uses under apps/studio/src (baseline 24).`, [frontend-tests.log](frontend-tests.log)), so there is nothing to lower. |
| 7 | Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas | [screenshots/](screenshots/) has 39 images: 13 views, each `-light`, `-dark` (system) and `-chosen-dark`. The views are the six settings pages, an Editor's Theme, the Settings switcher open (Owner and Editor), both confirmations, a toast and a new invite. They follow `docs/design/README.md`: `Org / Settings ▾ / **Members ▾**`, a panel per form, and table cards. |
| 8 | axe reports zero AA violations on the changed pages in both Appearances | [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` and `wcag22aa`, on 13 views × 3 Appearances, **0 violations**. |
| 9 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams are above. `make test-frontend`: 74 files, **949 tests**, 100% statements (4336/4336), branches (2992/2992), functions (1557/1557) and lines (3814/3814). |
| 10 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | No new domain term. **Breadcrumb** now names the Organisation settings areas among its switchers. No decision changed: ADR-0013 already says navigation is the breadcrumb and tabs go. |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `5f236f6`, which is `origin/candidate-reskin` (`61c67f3`, still its tip at the time) plus this branch. Each log's first line names its command and commit. GitHub Actions is down, so these are local.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 74 files, 949 tests, 100%. `embed.js` is 778 B gzipped. 24 palette-class uses (baseline 24). | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` (Chrome) | exit 0, 14 passed | [e2e-harness.log](e2e-harness.log) |
| Screenshots and axe | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 39 screenshots, 0 axe violations. | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack.** There is no Docker daemon in this sandbox, so the backend, the settings Playwright specs and `e2e/harness/axe.spec.ts` against the stack were not run. The specs type-check and lint. The helper they call is checked by the harness spec in Chrome. [shots.test.ts](shots.test.ts) stands in for the axe run: it serves the built Studio, answers the API with the unit tests' MSW fakes, and runs the same axe tags. No backend code changed.
- **Credential row actions stay buttons**, not a ⋯ menu. The ticket names only the Badge and the `ConfirmDialog` for Credentials, and the buttons keep the names that e2e specs and Members use ("Check now: X", "Rotate key: X", "Delete: X").
- **No pixel comparison.** The design canvas could not be opened from this sandbox. The comparison is against `docs/design/README.md` and the patterns.
- **Concurrent tickets.** 11-05 and 11-12 are in flight on their own branches. 11-05 also edits `StudioBreadcrumb.tsx` and the helpers' `TAB_ROWS`. Whichever lands second merges the other in, and the gate is re-run.
