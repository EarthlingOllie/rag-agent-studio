# Evidence: ticket 11-02, foundation: tokens, fonts and Appearance

Branch `ticket/11-02-foundation-tokens-fonts-appearance`, from `origin/candidate-reskin` at `e3fd977` (the merge of 11-01, #82). The claim commit `17c983f` set Status `in-progress`. The feature is one commit, `9e785b8`. The last commit changes only this folder and the ticket file. No backend code, no route, no markup and no accessible name changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are at the end.

## What was built

- **Tokens:** `apps/studio/src/index.css` imports `./design/tokens.css` straight after `tailwindcss`. That brings the token utilities (`bg-canvas`, `text-ink`, `border-line`…), the light and dark token values, and the base layer: `body` takes `canvas` and `ink`, `:focus-visible` draws a 2px `accent` ring, and `::selection` uses `accent-soft`.
- **Fonts:** `apps/studio/index.html` preconnects to Google Fonts and loads Instrument Sans (400, 500, 600) and IBM Plex Mono (400, 500) with `display=swap`; `tokens.css` names them as `--font-sans` and `--font-mono`.
- **Appearance before first render:** `main.tsx` calls `initAppearance()` before `createRoot(...).render`, so a Member's stored choice (`localStorage` `studio.appearance`) is on `<html data-appearance>` before anything is drawn. With no choice, there is no attribute and the system preference decides.
- **Markdown styles** (the Document viewer) use tokens: `border-line` for table cells, and `bg-sunken text-ink` for `code` and `pre`. `text-ink` is new: on the sunken fill the surrounding text colour may not contrast while a page is still on palette colours.
- **Palette ratchet:** `frontend/palette-baseline.json` is lowered from 639 to **636** (the three markdown classes).
- **Skill:** `.claude/skills/studio-reskin/PATTERNS.md` R0 mentions the `text-ink` on `code` and `pre`.

**Moved actions: none.** No control, link or route moved.

## Test seams

The [shared test seams](../../../specs/README.md#shared-test-seams) and spec 11's Testing Decisions; not confirmed with a human (none available). Written test first: each new test failed before the change it covers.

- **The Studio's entry point** (`main.test.tsx`, network seam with the default MSW handlers): the Studio opens in the light or dark Appearance the Member chose, read from `<html>` at the moment the Studio first puts anything in `#root` (a `MutationObserver`, so no internals are mocked); with no choice, `<html>` has no `data-appearance` and the system decides.
- **The page contract** (`foundation.test.ts`, like the token contract test it reads the files from disk, because under Vitest CSS imports are empty and `index.html` is never loaded): `index.css` imports exactly `tailwindcss` then `./design/tokens.css`; `index.html` loads Instrument Sans and IBM Plex Mono and preconnects to `fonts.gstatic.com`, the families `tokens.css` names; the body background and text colour are `canvas` and `ink` and the focus ring is `accent`; every colour utility in the markdown styles is a token, with `code` and `pre` on `bg-sunken text-ink`.
- **In a browser** ([shots.mjs](shots.mjs)): screenshots and axe, see below.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | `index.css` imports `design/tokens.css`; `index.html` loads Instrument Sans and IBM Plex Mono | `foundation.test.ts` (first two tests). In Chrome every page's body font is `"Instrument Sans"` ([shots-axe.log](shots-axe.log)), and the markdown `code` renders in IBM Plex Mono ([document-viewer-light.png](screenshots/document-viewer-light.png)). |
| 2 | `initAppearance()` runs before the first render, so no page flashes the other Appearance | `main.test.tsx`: "opens in the light/dark Appearance the Member chose, before anything is drawn" and "follows the system until the Member chooses". In Chrome, with the system set to light and the choice stored as dark, every page has `data-appearance="dark"` and the dark canvas (`rgb(14, 22, 21)`) ([shots-axe.log](shots-axe.log), `chosen-dark` rows). |
| 3 | The page background, text colour and focus ring come from tokens; the markdown styles in `index.css` use tokens | `foundation.test.ts` (last two tests). In Chrome the body background is `canvas`: `rgb(243, 246, 246)` light, `rgb(14, 22, 21)` dark ([shots-axe.log](shots-axe.log)). The pages' own full-height wrappers still paint their palette background over it until the colour codemod (11-03), which is why the pages otherwise look the same. |
| 4 | Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR | No route, markup, handler or accessible name changed (the diff touches `index.html`, `index.css`, `main.tsx`, two tests and the baseline). All 935 existing and new tests pass. Moved actions: none (stated in the PR). |
| 5 | The palette ratchet baseline is lowered to the new count | `palette-baseline.json` 639 → 636; `make test-frontend` ends "636 palette-class uses under apps/studio/src (baseline 636)." ([frontend-tests.log](frontend-tests.log)) |
| 6 | Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas | [screenshots/](screenshots/): sign-in, sign-up, status, projects, documents and document-viewer, each `-light`, `-dark` (system dark) and `-chosen-dark`. Every page gets the new fonts and base layer; the Document viewer is the one page whose colours change (its markdown). Against the canvas: the fonts and the markdown's token colours match the *Direction* page; the rest of each page is unchanged by design until 11-03. |
| 7 | axe reports zero AA violations on the changed pages in both Appearances | [shots-axe.log](shots-axe.log): the e2e harness's tags (`wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`) on all six pages in light, system dark and chosen dark: **0 violations**. (Before `text-ink` was added, the dark Document viewer had one `color-contrast` violation on `code`; that is why it is there.) |
| 8 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams above. `make test-frontend`: 74 files, **935 tests**, 100% statements (4317/4317), branches (2971/2971), functions and lines ([frontend-tests.log](frontend-tests.log)). |
| 9 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | No new terms: **Appearance** is already defined. No decision changed: ADR-0013 already records the token stylesheet and the per-browser Appearance on `<html data-appearance>`; this ticket only switches them on. |

## Results

Run by [run-checks.sh](run-checks.sh) in the ticket's worktree at `9e785b8` (each log's first line names its command and commit). GitHub Actions is down, so these are local.

| Check | Command | Result | Log |
|---|---|---|---|
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint, tsc) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0: 74 files, 935 tests, 100%; `embed.js` 778 B gzipped; 636 palette-class uses (baseline 636) | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0: 2105 relative links resolve | [link-check.log](link-check.log) |
| Screenshots and axe | `node shots.mjs` (built Studio in Chrome) | exit 0: 18 screenshots, 0 axe violations | [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack:** there is no Docker daemon in this sandbox, so the backend, the Playwright suite and `e2e/harness/axe.spec.ts` were not run. [shots.mjs](shots.mjs) stands in: it serves the built Studio with fixed API fixtures (the unit tests' Ada, *HR handbook* Project and `handbook.pdf`) and runs the same axe tags in Chrome. This ticket changes no backend code.
- **Dark looks mostly light until 11-03:** the Appearance mechanism works (the tokens switch, the body is dark, the choice applies before rendering), but every page still paints its own `bg-slate-50`/`bg-white` wrappers and slate text, as the ticket requires ("no other visible change"). The colour codemod (11-03) moves those to tokens.
- The test seams were not confirmed with a human; the spec's own seams were used.
- The design canvas could not be opened from this sandbox to compare pixel for pixel; the comparison is against `docs/design/README.md` and the R0 slice in the `studio-reskin` skill.
