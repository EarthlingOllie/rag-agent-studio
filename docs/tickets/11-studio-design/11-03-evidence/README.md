# Evidence: ticket 11-03, colour codemod

Branch `ticket/11-03-colour-codemod`, from `origin/candidate-reskin` at `aca809b` (the merge of 11-02, #83). The claim commit `88eb26d` set Status `in-progress`. Then:

- `1cb2d98` adds the one-off codemod (`frontend/scripts/colour-codemod/`: `codemod.mjs`, `cli.mjs` and `codemod.test.mjs`, 14 tests, 100% line, branch and function coverage under `node --test`).
- `b99b1d5` is the codemod's output, and nothing else: 49 files, 438 class-list lines changed, plus `palette-baseline.json`.
- `2551e7a` is one non-colour class fix: the Document row actions (Retry, Delete) get `min-h-6`. axe's WCAG 2.2 target-size rule flagged them once the fixture had more than one row.
- `0cc9ce8` deletes the codemod.
- The last commit changes only this folder and the ticket file.

No backend code, route, markup, text, handler, accessible name or test changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

The codemod applies the class-mapping table in `.claude/skills/studio-reskin/PATTERNS.md` to every string literal under `apps/studio/src`. It skips tests, test helpers and `design/`. It also covers `packages/ui/src/MarkdownEditor.tsx`, a Studio-only editor (the widget does not use it) that the Instructions page and the Agent's Draft render. A variant (`hover:`, `disabled:`, `focus:`, `aria-pressed:`, `[&_code]:`…) is kept on the mapped class. [codemod.log](codemod.log) is its run.

| Palette class | Token | Note |
|---|---|---|
| `bg-slate-50` | `bg-canvas` | The table says "nothing" for page wrappers. `bg-canvas` paints the same colour and keeps the change to a swap. |
| `hover:bg-slate-50`, `hover:bg-slate-100`, `bg-slate-100`, `bg-slate-200` | `hover:bg-sunken`, `bg-sunken` | |
| `bg-white` | `bg-surface` | |
| `text-slate-900`, `text-slate-800` | `text-ink` | |
| `text-slate-700` | `text-ink-2` when its class list sets a font weight (labels), otherwise `text-muted` | **Judgement call** (the table offers both) |
| `text-slate-600`, `text-slate-500` | `text-muted` | |
| `border-slate-200` / `-100`, `divide-slate-200` | `border-line` / `border-line-soft`, `divide-line` | |
| `border-slate-300`, `border-slate-400` | `border-field` | |
| `bg-slate-900` + `text-white`, `hover:bg-slate-700` | `bg-accent` + `text-on-accent`, `hover:bg-accent-hover` | Primary buttons |
| `disabled:bg-slate-500/600` | `disabled:bg-muted` | **Judgement call** |
| `focus:outline-slate-900` / `-500` | `focus:outline-accent` | |
| `bg-red-700` + `text-white`, `hover:bg-red-800` | `bg-danger` + `text-on-danger`, `hover:bg-danger/90` | Destructive confirm. **Judgement call** for the hover. |
| `text-red-700/800/900`, `border-red-300/700/800`, `border-red-200`, `bg-red-50/100` | `text-danger`, `border-danger`, `border-danger-soft`, `bg-danger-soft` | |
| `bg-green-50/100`, `bg-emerald-100`, `text-green-900`, `text-emerald-800/900`, `border-green-200` | `bg-accent-soft`, `text-accent-ink`, `border-accent-soft` | Success |
| `bg-amber-50/100`, `text-amber-800/900/950`, `border-amber-300/500`, `border-amber-200` | `bg-flag-soft`, `text-flag`, `border-flag`, `border-flag-soft` | Warning and flag |
| `bg-slate-700` (Token Budget meter fill) | `bg-chart-1` | **Judgement call**: data colour |
| `[&_a]:text-blue-800` (Markdown editor links) | `[&_a]:text-accent` | Links in running text |

**Left for review (the codemod's own list):** the codemod could not map `border-slate-700` with confidence. It is the drag-over border of the Documents drop zone, and a test asserts it. It is unchanged.

**Pinned by tests.** Tests may not change in this ticket, and three classes are asserted with `toHaveClass`:

- `DocumentsTab.tsx:131` `border-slate-700`: left as it is.
- `DocumentsTab.tsx:170` `text-slate-700`: the class stays, and `text-muted!` is added after it.
- `VersionComparison.tsx:63` `bg-amber-50`: the class stays, and `bg-flag-soft!` is added after it.

Tailwind's important modifier makes the added token win whatever the stylesheet order. Without it, the dark Analytics comparison table failed `color-contrast` (light ink on `amber-50`); the first axe run showed this. Tickets 11-06 and 11-10 should change those assertions to behaviour and drop the palette class.

**Remaining palette count, by file (24):**

- 3 real uses, in non-test code:
  - `projects/DocumentsTab.tsx` (2): lines 131 and 170, above. These are for 11-06.
  - `projects/VersionComparison.tsx` (1): line 63, above. This is for 11-10.
- 6 in test assertions:
  - `projects/DocumentsTab.test.tsx` (3)
  - `projects/AnalyticsTab.test.tsx` (3)
- 15 false positives, which are not classes:
  - `test/theme.ts` (6), `projects/AgentBranding.tsx` (2), `projects/AgentBranding.test.tsx` (3) and `settings/ThemePage.test.tsx` (1) are `dark:` keys of the widget Theme's colour objects.
  - `design/tokens.css` (3) is a comment.

  The ratchet's regex counts them. 11-13 has to exclude or reword them to reach zero.

**Not class lists, so left:** `TimeSeriesChart.tsx` passes hex colours to Recharts (`#e2e8f0` grid, `#334155` ticks, `#1d4ed8` line, `#b45309` markers). Those are props, not classes. 11-10 moves them to `chart-1` and tokens.

**Moved actions: none.** No control, link or route moved. The visible change is colour only: primary buttons turn sea-glass (`accent`), success and warning notices take the accent-soft and flag tokens, and every page follows the Appearance.

## Test seams

There is no new runtime behaviour: class lists changed, logic did not. The existing 935 Studio tests, which find everything by role and name, are the behavioural check, and they all pass unchanged. The codemod was itself written test first (red, then green) as a script, like the palette ratchet: fixture strings and a fixture tree with known mappings, pins, skipped tests and design-system files. It is deleted with its tests (`0cc9ce8`), as the ticket asks. The seams were not confirmed with a human (none available); the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | A one-off script applies the class-mapping table from the `studio-reskin` skill across `apps/studio/src`; it is committed with the PR and then deleted | Added in `1cb2d98`, applied in `b99b1d5` ([codemod.log](codemod.log)), deleted in `0cc9ce8`. The table is above. |
| 2 | Only class lists change: no markup, text, routes or tests change | `git diff aca809b..0cc9ce8 --word-diff` shows only class tokens changed in 49 source files. No `*.test.*` or e2e file is in the diff; `router.tsx` changes only its root wrapper's class lists, no route. The single non-mapping class change is `min-h-6` (commit `2551e7a`, below). |
| 3 | Ambiguous mappings are left for review and listed in the PR | `border-slate-700` is left. The judgement calls (`text-slate-700` split, meter fill, disabled fills, danger hover) and the three test pins are listed above and in the PR. |
| 4 | The palette count falls substantially; anything left is listed by file for the area tickets | 636 to **24** (96%). By-file list above: 3 real uses, for 11-06 and 11-10. |
| 5 | Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR | All 935 tests pass unchanged. Moved actions: none. `min-h-6` only enlarges the row-action hit area. |
| 6 | The palette ratchet baseline is lowered to the new count | `palette-baseline.json` 636 to 24. `make test-frontend` ends "24 palette-class uses under apps/studio/src (baseline 24)." ([frontend-tests.log](frontend-tests.log)) |
| 7 | Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas | [screenshots/](screenshots/): 26 pages (every Studio route: signed-out, Projects, all six Project sections, Document viewer, Agent, Conversation, Cost, Profile, Security, all six Organisation settings), each `-light`, `-dark` (system) and `-chosen-dark`, 78 in all. Colours now match the canvas's token roles (canvas, surface, ink, muted, accent primary, flag, danger) in both Appearances. Layout still follows the old screens until 11-04 to 11-12. |
| 8 | axe reports zero AA violations on the changed pages in both Appearances | [shots-axe.log](shots-axe.log): the e2e harness's tags (`wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`) on all 26 pages in light, system dark and chosen dark: **0 violations**. |
| 9 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams above. `make test-frontend`: 74 files, **935 tests**, 100% statements (4317/4317), branches (2971/2971), functions and lines ([frontend-tests.log](frontend-tests.log)). |
| 10 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | No new terms. No decision changed: ADR-0013 already says pages use tokens only. |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `0cc9ce8`, which is `origin/candidate-reskin` (`aca809b`) plus this branch. Each log's first line names its command and commit. GitHub Actions is down, so these are local.

| Check | Command | Result | Log |
|---|---|---|---|
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint, tsc) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0: 74 files, 935 tests, 100%; `embed.js` 778 B gzipped; 24 palette-class uses (baseline 24) | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0: 2124 relative links resolve | [link-check.log](link-check.log) |
| Screenshots and axe | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (built Studio in Chrome) | exit 0: 78 screenshots, 0 axe violations | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack:** there is no Docker daemon in this sandbox, so the backend, the Playwright suite and `e2e/harness/axe.spec.ts` were not run. [shots.test.ts](shots.test.ts) stands in. It serves the built Studio and answers the API with the unit tests' own MSW fakes (`apps/studio/src/test`), through MSW's `getResponse`, and runs the same axe tags in Chrome. This ticket changes no backend code.
- **Pinned classes:** the three test-pinned palette classes stay until 11-06 and 11-10 rewrite those assertions (see above).
- **Chart colours:** the Recharts hex colours in `TimeSeriesChart.tsx` are props, not class lists. They are left for 11-10. The axis ticks are dim on the dark canvas, but axe does not flag them.
- **Several accent buttons:** a page with more than one old `bg-slate-900` button (for example Settings forms) now shows more than one accent button. The area tickets choose each view's one primary.
- **No pixel comparison:** the design canvas could not be opened from this sandbox, so there is no pixel-for-pixel comparison. The comparison is against `docs/design/README.md` and the token roles.
