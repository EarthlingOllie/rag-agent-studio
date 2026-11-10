# Evidence: ticket 12-01, dropdown chevron token and base rule

Local branch `t/12-01` (the convention's `ticket/12-01-select-chevron`), from `origin/candidate-reskin` at `63a7569`. The claim commit `47f1725` set Status `in-progress`; the feature is `9aa45b4` and `d6afbc1`; the last commit adds this folder, ticks the criteria and sets Status `done`. No backend code changes.

**Status: done.** Every criterion is met and evidenced below. Gaps are at the end.

## What was built

- **Token:** `--ds-chevron` in `design/tokens.css`, declared in the light, system-dark and chosen-dark blocks: a `data:` SVG of the Icon component's `chevronDown` path (24×24, 1.8 stroke), stroked in each Appearance's `muted` (`#536260` light, `#93a5a2` dark).
- **Base rule** (`tokens.css`, outside every layer so a recipe's `px-*` can't take the room back): `select:not([multiple])` has `appearance: none`, draws `var(--ds-chevron)` 16px wide at `right var(--select-inset, 0.75rem) center`, and has `padding-right: max(2.25rem, inset + 1.5rem)`. A disabled select has `opacity: 0.5` (like a disabled button), so the chevron dims with the field.
- **Recipes:** every select recipe sets `--select-inset` to its own left padding: `field.select` (12px), `field.pill` (14px) and the new `field.selectCompact` (10px, table cells). `field.pill` lost its `mt-1`; `field.filter` gained `gap-1`, so the pill sits the same under a filter label and also works on its own (the Documents status filter).
- **Pages onto recipes:** Members' role select (`field.selectCompact`), the Audit filters (`field.filter` labels over `field.pill`), the Documents status filter (`field.pill`), Embedding Model and Cost's "Break down by" (`field.select`, off the legacy `INPUT`). The Draft editor already used `field.select` (imported as `fields`).
- **Docs:** `docs/design/README.md` (Shape and space: Selects) and `.claude/skills/studio-reskin/PATTERNS.md` (the replacement table).

## Test seams

The [shared test seams](../../../specs/README.md#shared-test-seams); not confirmed with a human (none available), the spec's Testing Decisions were used. Each test was written first and failed before its change.

- **Token contract test** (`design/tokens.test.ts`, exists): the chevron token is declared in all three blocks and the system dark matches the chosen dark; it draws the chevron-down path stroked in each Appearance's `muted`. Colour-only checks skip the image token.
- **Stylesheet contract** (`foundation.test.ts`, reads `tokens.css` from disk): the select rule's appearance, image, position from `--select-inset`, ≥36px right padding, disabled opacity, and that it sits outside the layers.
- **Recipes and sources** (`selects.test.ts`): every `<select>` under `apps/studio/src` takes its class from `field.select`, `field.pill` or `field.selectCompact` (none from its own string), and each recipe's `--select-inset` equals its left padding.
- **End-to-end** (`e2e/tests/select-chevron.spec.ts`): on the Members page, the invite form's Role and a Member's role select compute `appearance: none`, right padding ≥36px, the chevron image at `calc(100% - <left padding>)`, and a different chevron in the dark Appearance. Not run here (no compose stack); [shots.test.ts](shots.test.ts) runs the same check on every select of every signed-in page.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Every single-value select draws the chevron-down instead of the browser's arrow | Base rule; `foundation.test.ts`. In Chrome every select on every signed-in page computes `appearance: none` with the chevron image ([selects.log](selects.log)); e.g. [settings-members-light.png](screenshots/settings-members-light.png), [conversations-light.png](screenshots/conversations-light.png), [agent-playground-light.png](screenshots/agent-playground-light.png). |
| 2 | Chevron inset mirrors the text's left inset; ≥36px right padding | `selects.test.ts` (inset = left padding per recipe), `foundation.test.ts`. [selects.log](selects.log): every select's chevron is at `calc(100% - <its padding-left>)` and its right padding is 36px (12px inset) or more (38px pill). |
| 3 | Chevron colour from a new token with light, system-dark, chosen-dark values; visible in both Appearances | `tokens.test.ts`. [selects.log](selects.log): stroke `#536260` in light, `#93a5a2` in system dark and chosen dark; `muted` meets 4.5:1 on `surface` in both (existing token pairs). Dark screenshots, e.g. [settings-members-dark.png](screenshots/settings-members-dark.png). |
| 4 | A disabled select dims its chevron along with the field | `foundation.test.ts`; [selects.log](selects.log): a disabled role select computes opacity 0.5 in all three Appearances; [select-disabled-light.png](screenshots/select-disabled-light.png), [select-disabled-dark.png](screenshots/select-disabled-dark.png). |
| 5 | `field` gains a compact select; no page keeps its own select class string | `field.selectCompact`; `selects.test.ts` scans every select. Members, Audit, Documents, Embedding Model and Cost moved onto recipes. |
| 6 | Token contract test checks the chevron token in all three blocks, system-dark = chosen-dark | `tokens.test.ts` "the select chevron". |
| 7 | An end-to-end check finds `appearance: none` and right padding ≥36px | `e2e/tests/select-chevron.spec.ts` (listed in [e2e-list.log](e2e-list.log)); the same check in Chrome on the built Studio for every select ([selects.log](selects.log)). |
| 8 | Design system only; palette ratchet passes | Tokens and recipes only; `make test-frontend` ends "0 palette-class uses under apps/studio/src (none allowed)." ([frontend-tests.log](frontend-tests.log)) |
| 9 | Evidence: light and dark screenshots, wide (1440) and narrow (390), axe in both Appearances | [screenshots/](screenshots/): every signed-in page `-light`, `-dark`, `-chosen-dark` at 1440, and `-narrow-light`, `-narrow-dark` at 390. [shots-axe.log](shots-axe.log): **0 axe violations**, no horizontal overflow. |
| 10 | Tests at the highest seam; 100% line and branch coverage | Seams above. `make test-frontend`: 80 files, 1042 tests, 100% statements (4554/4554), branches (3228/3228), lines ([frontend-tests.log](frontend-tests.log)). |
| 11 | New domain terms in `GLOSSARY.md`; ADRs updated if a decision changed | No new domain terms (a chevron is UI, not domain). No decision changed: ADR-0013's token stylesheet gains one token; the rule is recorded in `docs/design/README.md`. |

## Results

Run by [run-checks.sh](run-checks.sh) in the ticket's worktree (each log's first line names its command and commit). Local, not CI.

| Check | Command | Result | Log |
|---|---|---|---|
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0: 80 files, 1042 tests, 100%; ratchet 0 | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| New e2e spec parses | `playwright test --list` | exit 0: 1 test | [e2e-list.log](e2e-list.log) |
| Screenshots, axe, selects | `vitest run --config shots.config.mjs` (built Studio in Chrome) | exit 0: 118 screenshots, 0 axe violations, no overflow, 230 selects drawn right, 0 wrong ([shots.log](shots.log)) | [shots-axe.log](shots-axe.log), [selects.log](selects.log) |

## Gaps

- **No compose stack:** no Docker daemon in this sandbox, so the backend, the Playwright suite (including the new `select-chevron.spec.ts`) and the e2e axe sweep were not run. [shots.test.ts](shots.test.ts) stands in, as in 11-13: the built Studio with the unit tests' MSW fakes, the same axe tags, and the spec's select check on every select.
- **Overlap with parallel tickets:** Embedding Model (12-06) and Cost (12-04) each had one select line moved from the legacy `INPUT` to `field.select`; those tickets rewrite the pages, so a merge keeps their version as long as it uses a select recipe.
- Test seams not confirmed with a human.
