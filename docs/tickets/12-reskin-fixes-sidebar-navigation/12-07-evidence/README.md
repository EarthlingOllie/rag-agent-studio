# Evidence: ticket 12-07, Remove the legacy BUTTON / INPUT strings

Branch `t/12-07`, from `t/12-03` at `d91484d` (12-03 on top of `claude/gallant-euler-zxqfxb` at `d302125`, which holds 12-01, 12-02, 12-04, 12-05, 12-06 and 12-08). The claim commit `9a5cec9` set Status `in-progress`. Then:

- `1752fc2` is the change: `projects/AgentBranding.tsx` on the `button` and `field` recipes, `projects/ProjectsPage.tsx` without its `BUTTON` / `INPUT` exports, `projects/DraftEditor.tsx` without its `CONFLICT_BUTTON` alias, and a test in `projects/ProjectsPage.test.tsx`.
- `9c13646` holds this folder's scripts, and `c9da16b` makes [run-checks.sh](run-checks.sh) write one log per frontend check.
- `3d9dcf5` was the first evidence commit (Status `done`).
- `3777a67` fixes a page-local input string the first round missed: `settings/ThemePage.tsx` had `SHORT` (a copy of `field.inputMono`) and `FIELD_ERROR`. Both are gone; a guard test is added (`design/recipes.test.ts`), and [shots.test.ts](shots.test.ts) now covers the Theme page.
- The last commit changes only this folder and the ticket file.

No backend code, route, API call, query shape, permission or visible text changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

- **Projects page module.** `ProjectsPage.tsx` no longer defines or exports `BUTTON` and `INPUT`. Its other export, `useOrganisationRole`, is unchanged.
- **Remaining importers.** Agent branding was the last one: the Embedding Model setting (12-06) and Organisation cost (12-04) had already moved to the recipes. Agent branding now uses:
  - Save colours: `button.primary` (the section's one primary action);
  - Upload / Replace avatar (the file-picker label): `button.secondary`, with the disabled and focus-visible states carried through `has-[…]` from its hidden input;
  - Remove avatar: `button.danger`;
  - the hex colour fields: `field.inputMono` (`aria-invalid` gives the danger border), under `field.hint`-sized labels;
  - the Override checkboxes: `field.checkbox`;
  - "Use colours like #1a2b3c." and a failed avatar action: `field.error`; muted lines: `text.muted`.
- **No page-local button or input strings.** `DraftEditor.tsx`'s `CONFLICT_BUTTON` (an alias of `button.secondary`) is inlined. The Theme page (`settings/ThemePage.tsx`) defined `SHORT`, a copy of `field.inputMono` used by its hex colour fields and its corner-radius field, and `FIELD_ERROR` for their errors. The first round missed them; `3777a67` moves both fields to `field.inputMono` and their errors to `field.error`, and deletes both constants. The recipe is full width, so each field sits in a `w-28` box (a `w-28` on the input itself loses to the recipe's `w-full` in the built CSS, which also left Agent branding's hex fields full width; they get the same box on their label). The Theme page's colour swatch (`<input type="color">`) is a native picker styled in place, with no shared string to replace. A guard test (below) now finds no module-level control class string outside `design/`; `cost/CostPage.tsx`'s `TOTAL_ROW` is a table-row style, not a button or input.

## Test seams

The spec's network seam (`renderStudio` with MSW). Behaviour is frozen, so the existing `AgentBranding.test.tsx` (colours, invalid hex, 422, avatar upload / replace / remove, Editor view) and `DraftEditor` tests pass unchanged. One test was added first and failed (red), then passed after the change:

- `projects/ProjectsPage.test.tsx`, "the Projects page leaves button and field styling to the design system's recipes": the module exports neither `BUTTON` nor `INPUT`. Type-checking pins that no importer is left.
- `design/recipes.test.ts`, "no Studio page defines its own button or input class string": reads every non-test module under `apps/studio/src` outside `design/` and fails on a module-level class string that draws a control's box (a fixed `h-8` to `h-11` height and `rounded`). Red with `["settings/ThemePage.tsx"]` before `3777a67`, green after.

The Theme page's behaviour is unchanged: `settings/ThemePage.test.tsx` (invalid hex, radius out of range, save, Editor view) passes unchanged.

The seams were not confirmed with a human (none was available), so the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | Agent branding and any remaining importer use the design system's button and field recipes | `AgentBranding.tsx` imports `button`, `field`, `surface`, `text` from `../design` and nothing from `./ProjectsPage`. No other file imported `BUTTON` / `INPUT`: [typecheck.log](typecheck.log) (`tsc`, exit 0) would fail on a dangling import. Screenshots `branding-*`. |
| 2 | The Projects page no longer exports BUTTON and INPUT; nothing in the Studio defines its own button or input class string | `ProjectsPage.tsx` and the new `ProjectsPage.test.tsx` test; `DraftEditor.tsx` alias removed; `settings/ThemePage.tsx`'s `SHORT` and `FIELD_ERROR` replaced by `field.inputMono` and `field.error` (`3777a67`); the guard test `design/recipes.test.ts`. Screenshots `theme-*`. |
| 3 | Agent branding is checked in both Appearances, wide and narrow | [screenshots/](screenshots/) and [shots-axe.log](shots-axe.log): 4 views × wide and narrow × light, dark and chosen dark. |
| 4 | Design system only, no palette classes or `dark:`; the palette ratchet passes | Only recipes plus layout utilities. [palette-ratchet.log](palette-ratchet.log): "0 palette-class uses under apps/studio/src (none allowed)", exit 0. |
| 5 | Light and dark screenshots, wide (1440) and narrow (390), and the axe sweep in both Appearances | [screenshots/](screenshots/): Agent branding on the Agent's Embed view as an Owner with no override, with a saved colour override and an avatar, with a colour that isn't hex (the error and invalid field), and as an Editor; and the Theme page (Organisation settings, Theme) as an Owner, with a hex colour and a corner radius that aren't valid (both errors and invalid fields), and as an Editor (read-only) = 7 views × 2 widths × 3 Appearances = 42 images. [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`, **0 violations**, no horizontal scroll. |
| 6 | Tests at the highest seam; 100% line and branch coverage holds | Seams above. [test.log](test.log): 82 files, 1074 tests passed; statements 4610/4610, branches 3261/3261, lines 4034/4034 (100%). |
| 7 | New domain terms in `GLOSSARY.md`; ADRs updated if a decision changed | No new domain term (Agent, Theme override, Owner, Editor are defined). No decision changed. |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `3777a67`, the commit before the evidence commit (which changes only Markdown and logs). `make link-check` was rerun after the evidence was on disk. Each log's first line names its command and commit. GitHub Actions is not used, so these are local.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint | `pnpm lint` (eslint, `--max-warnings=0`, e2e included) | exit 0 | [lint.log](lint.log) |
| Type-check | `pnpm typecheck` (`tsc`) | exit 0 | [typecheck.log](typecheck.log) |
| Tests and coverage | `pnpm test` (`vitest run --coverage`) | exit 0. 82 files, 1074 tests passed, 100% statements, branches, lines | [test.log](test.log) |
| Embed budget | `pnpm check-embed-size` | exit 0. `embed.js` 1367 bytes, 778 gzipped (budget 2048 and 1024) | [check-embed-size.log](check-embed-size.log) |
| Palette ratchet | `pnpm palette-ratchet` | exit 0. 0 palette-class uses; ratchet tests at 100% | [palette-ratchet.log](palette-ratchet.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` (Chrome) | exit 0. 14 passed | [e2e-harness.log](e2e-harness.log) |
| Screenshots and axe | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 42 screenshots, 0 axe violations, no horizontal scroll. | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack.** The Docker daemon is not running in this sandbox, so the backend, the `branded-widget` Playwright spec and `e2e/harness/axe.spec.ts` against the stack were not run. [shots.test.ts](shots.test.ts) stands in for the axe run: it serves the built Studio, answers the API with the unit tests' MSW fakes, and runs the same axe tags. No backend code changed.
- **Concurrent tickets.** 12-09 and 12-10 change the shell and Agent pages in sibling branches; the screenshots show this branch's shell (breadcrumb and sidebar from 12-08). No shared navigation helper or `GLOSSARY.md` was edited here.
