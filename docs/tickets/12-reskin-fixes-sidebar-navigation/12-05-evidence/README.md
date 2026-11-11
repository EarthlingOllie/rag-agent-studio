# Evidence: ticket 12-05, Invite dialog

Branch `t/12-05`, from `origin/candidate-reskin` at `6d7182e`. The claim commit `4e623e5` set Status `in-progress`; `d18b92a` builds the dialog; `9690c82` keeps it open while the invite is sent (evaluator round 1); the last commit adds this folder, ticks the criteria and sets Status `done`.

No backend code, API call, route or permission changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

- **`settings/MembersPage.tsx`**: the inline `InviteForm` panel is removed. The Members heading row carries **Invite someone** (`button.primary`) on the right. It opens `InviteDialog`: the design system's `Dialog` without the corner ✕ (as `NewAgentDialog` and 12-02's Project details dialog), holding a form named "Invite someone" with `FormError`, Email (`field.input`, required), Role (`field.select`), "Email the invite link" (`field.checkbox`), then Cancel (`button.secondary`) and Invite (`button.primary`, "Inviting…" while pending). While the invite is sent, Cancel is disabled and Escape or a click outside does nothing, so the dialog can't unmount before the answer and the single-use Invite Link is never lost. The existing error mapping is unchanged: 409 with a detail (an existing Member, an Invite already pending), 422 (invalid email), anything else "Something went wrong. Try again." — all shown inside the dialog, which stays open and keeps what was typed.
- On success the dialog closes (focus returns to Invite someone), the toast "Invited …" fires, and the existing copy-link panel (`surface.panel`, region "New invite", with the expiry) renders above Pending invites. New link on a pending invite sets the same panel in the same place.
- **e2e specs** that invite (`invites`, `members`, `credentials`, `projects`, `require-mfa`) click **Invite someone** before filling the form; `invites.spec.ts`'s `openMembers` waits for the button instead of the form.
- **Docs**: `GLOSSARY.md` gains **Invite dialog**; `docs/design/README.md` *Settings and forms* describes Members with the dialog.

### Moved actions

| Before | After |
| --- | --- |
| Invite someone was an inline panel between Members and Pending invites | An Invite someone button in the Members header opens the invite dialog |

## Test seams

The spec's network seam (`renderStudio` with MSW, `MembersPage.test.tsx`); the seams were not confirmed with a human (none was available), so the spec's own were used. Written red first (12 failing, then green):

- "Members has a header with Invite someone, which opens a dialog with Email, Role and Email the invite link" (heading then button, before Pending invites; no inline form; Email focused and required; Role Editor; email box checked).
- "Cancel and Escape close the invite dialog without inviting, and focus returns to Invite someone" (no request; the dialog reopens empty).
- "Cancel and Escape don't close the dialog while the invite is sent, so the link isn't lost" (the request is held open; Cancel is disabled; Cancel and Escape leave the dialog in place; once released the toast and the "New invite" panel show). Written red first after evaluator round 1 (failed on Cancel not disabled), then green.
- "an Owner invites by email with a role and can copy the link" (the dialog closes; toast; the "New invite" panel with its expiry comes before the Pending invites heading; the next dialog starts empty).
- "a refused invite (%i) shows why", "an unreachable API…", "a duplicate invite…" (the alert is inside the dialog, which stays open with the email kept).
- "an Owner gets a new link for an expired invite" (the same panel, above Pending invites).

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | Members header with Invite someone as its primary action, top right; inline panel gone | Header test; `members-*` screenshots |
| 2 | Invite someone opens a dialog with Email, Role and "Email the invite link"; invalid email or existing Member reported inside it | Header test; refused tests (409 existing Member, 422 invalid email); `invite-dialog-*`, `invite-refused-*` |
| 3 | On success the dialog closes, the toast confirms, and the copy-link panel (with expiry) shows above Pending invites | Invite test; pending Cancel/Escape test (the panel still shows); `invite-link-*` |
| 4 | New link on a pending invite shows the same copy-link panel | New-link test; `new-link-*` |
| 5 | Cancel and Escape close the dialog without inviting; focus returns to Invite someone | Cancel/Escape test; pending Cancel/Escape test (blocked while sending, so an invite is never made behind a closed dialog); [shots-axe.log](shots-axe.log) keyboard lines in a real browser, all four runs |
| 6 | Design system only; the palette ratchet passes | Tokens and recipes only; [frontend-tests.log](frontend-tests.log) ends with 0 palette-class uses |
| 7 | Evidence: light and dark screenshots, wide (1440) and narrow (390), and the axe sweep in both Appearances | [screenshots/](screenshots/): 5 views × light, dark, narrow-light, narrow-dark (20 files); [shots-axe.log](shots-axe.log): **0 axe violations**, 0 overflows, 0 focus problems |
| 8 | Tests at the highest seam; 100% line and branch coverage | Seams above; [frontend-tests.log](frontend-tests.log): 1038 tests, 100% statements (4560/4560), branches (3232/3232), functions (1646/1646), lines (3988/3988) |
| 9 | New domain terms in `GLOSSARY.md`; ADRs updated if a decision changed | **Invite dialog** added after Invite Link; no ADR decision changed (ADR-0013's `Dialog` and toast patterns are used as they are) |

## Results

[run-checks.sh](run-checks.sh) ran these at `9690c82`. Each log's first line names its command and commit.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0; 79 files, 1038 tests, 100% coverage | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Changed e2e specs parse | `playwright test --project=studio --list` (the five changed specs) | exit 0 | [e2e-list.log](e2e-list.log) |
| Screenshots, axe, overflow, focus | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome, API answered by the unit tests' MSW fakes) | exit 0; 20 views, 0 violations | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack.** The backend and the Playwright `studio` suite (including the five specs updated to open the dialog) were not run; they lint, type-check and list. `shots.test.ts` stands in for the axe sweep on the page this ticket touches. **Closed after spec 12 merged:** the whole compose-stack suite (`make e2e`'s steps, 118 tests) passed against a stack built from the integration branch, with the fixes it needed; see [12-e2e-evidence](../12-e2e-evidence/README.md).
- **The row role select** (story 42, `field.selectCompact`) belongs to 12-01 ("Members' role select … move onto recipes") and is not in this ticket's criteria; it is unchanged here.
- **No pixel comparison** with the design canvas (not reachable from the sandbox).
