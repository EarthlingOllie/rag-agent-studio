# Evidence: ticket 11-10, Conversations and Analytics

Branch `ticket/11-10-conversations-analytics`, from `origin/candidate-reskin` at `cd2398c` (the merge of 11-08, #92). The claim commit `229fd11` set Status `in-progress`. Then:

- `3ced332` is the change itself: the Conversations list beside the transcript (also the Agent's Conversations view), the folded Trace, Analytics' Agent filter in the URL and "Analytics for this Agent", the KPI cards and the chart. It also adds `ConversationsAnalytics.test.tsx` and updates the unit tests. Palette baseline 19 → 15.
- `e1a2fd1` updates 8 end-to-end specs. `8a25302` updates `GLOSSARY.md` and `docs/design/README.md`.
- `e469dc0` adds this folder's scripts (and left-aligns two tables' row headers seen in the first screenshots). The last commit changes only this folder (the logs and screenshots of the run).

No backend code, API call or permission changes. Three routes are added (below).

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

**Conversations** (`projects/ConversationsTab.tsx`): the section heading, then one toolbar of pill filters (`field.filter` labels over `field.pill` controls, new recipes): Agent, Version, From (UTC), To (UTC), **Show** as a `Segmented` Visitors / Playground / Both, then Feedback, Rating and Guardrail (kept from 07-x and 08-x). Under it:

- **The list** (left, up to 380px): a card of compact items. Each item's link is the first question; under it the facts as a `<dl>`: started (mono), Agent, Visitor or a Playground pill (its title explains), the Versions that answered (mono), and labelled Messages, Feedback, Rating and Guardrail counts. The open Conversation is highlighted (`aria-current="page"`). `Pagination` ("Conversations pages") and "Page n of m · N Conversations" under it.
- **The transcript** (right), a panel: "Conversation with <Agent>" with its kind and times, Delete Conversation (Owners), the questions as bubbles on the right and the answers beside an avatar with a **Version chip** (`Badge kind="version"`, read "Version 2") or **Draft**, "Fallback reply", a **Blocked by guardrail** badge when the input Guardrail refused the question, the Visitor's feedback, and the **Trace folded under each answer** (`TraceFold`, summary "120 input and 6 output tokens · 85 ms", loaded the first time it opens). The Conversation Rating card follows. Before one is opened: an `EmptyState` "Choose a Conversation".
- The routes nest: `/conversations` (list) holds `/conversations/` (nothing open) and `/conversations/$conversationId` (the transcript), so the list stays mounted and keeps its filters (in the URL, as before) while Conversations are opened, and filtering or paging keeps the open one.

**The Agent's Conversations view** (`/agents/$agentId/conversations` and `/agents/$agentId/conversations/$conversationId`, new): the same component fixed to the Agent: no Agent filter, its Versions in the Version filter, an `agent=` in the URL ignored. The view crumb stays Conversations (also with a Conversation open) and the Agent crumbs stay.

**Analytics** (`projects/AnalyticsTab.tsx`, `TimeSeriesChart.tsx`, `VersionComparison.tsx`): the Agent is in the URL (`?agent=`; an unknown one falls back to the first, as before), one toolbar (Agent, Version, From, To), the range line, then:

- **KPI cards**: muted title, mono figure, the 95% interval and n under it; a small sample is dashed and muted with a **Low sample** `Badge` whose title says why ("Fewer than 30 votes").
- **Compare two Versions**: `table.wrap`, numbers mono, changed rows on `flag-soft` (was `bg-amber-50`), Export as CSV as a secondary button.
- **Over time**: a `chart-1` 2px area line with a 12% fill (`ComposedChart` + `Area`), horizontal `line-soft` gridlines, one y-axis; Live markers as dashed rules with a mono pill label; when Documents changed, a `flag-soft` band labelled with the warning icon and "Documents changed" plus the note under the chart; on hover a crosshair (dashed vertical cursor, dashed horizontal rule, ringed dot) and a readout ("Chart readout": period, value, n; "No data" for an empty day); **Show as: Chart / Table** swaps in the Table view. The figure is named by its caption.

**"Analytics for this Agent"**: a ghost link in the Agent header (every Agent view) to Analytics with `?agent=<id>`.

### Moved actions (behaviour otherwise unchanged)

| Before | After |
| --- | --- |
| The Conversations table, then a separate Conversation page | The list beside the open Conversation's transcript (same URLs) |
| "All Conversations" link on a Conversation | Gone: the list is beside it, with the same filters |
| Show: a select (Visitors and Playground / Visitors only / Playground only) | `Segmented` Visitors / Playground / Both |
| Previous page / Next page buttons | `Pagination` (the same Previous and Next, plus page numbers) |
| "Trace" button opening the Trace drawer | The Trace folds open under each answer (the drawer is gone) |
| "Agent Version v2 · fallback reply" text above an answer | A Version chip (or Draft badge), "Fallback reply", and a Blocked by guardrail badge |
| Delete Conversation, then an inline confirmation panel | A destructive `ConfirmDialog` "Delete Conversation" (confirm still "Yes, delete it") |
| Agent view switcher → Conversations: the Project's Conversations with `?agent=` | The Agent's own Conversations view, under the Agent's crumbs (the Project's list with `?agent=` still works) |
| Analytics' Agent kept in page state | In the URL, `?agent=`; each Agent links to it |
| (none) | "Analytics for this Agent" in the Agent header |
| "Low confidence (fewer than 30 votes)" text on a card | The Low sample badge, the reason in its title |
| Chart and its table both shown, the Live changes list | Chart or Table view; the list stays |
| "Loading the …" text | `Skeleton` with the same words |

API calls, permissions and the data shown are unchanged.

## Test seams

The spec's frontend seams:

- **Network seam:** `renderStudio` with MSW.
  - `projects/ConversationsAnalytics.test.tsx` (new, 12 tests): the list beside the transcript with the open one marked; the Show `Segmented`; `Pagination`; Version chips, the Blocked by guardrail badge and the folded Trace (loaded only when opened); the Agent's Conversations view (filtered, no Agent filter, its Versions offered, opening a Conversation keeps the Agent's crumbs, its filters in the URL without the Agent); Low sample badges with interval and n; Analytics' Agent from the URL; "Analytics for this Agent"; the Table view; labelled Live markers, the Documents band and one y-axis; the crosshair readout, including a day with no data.
  - Written red first: all 12 failed against the base. The readout test then found a real bug: Recharts drops a null point from the tooltip by default, so an empty day had no readout (`filterNull={false}`).
  - The existing `ConversationsTab`, `AnalyticsTab`, `TimeSeriesChart`, `AgentViews` and `ProjectPage` tests now read the list, the folded Trace, the badge and the Table view, with the same assertions on behaviour.
- **End-to-end seam:** 8 specs are updated but were not run (no stack): `conversations`, `conversation-rating`, `message-feedback`, `guardrail-analytics` (also checks the blocked badge), `retention`, `time-series` (Table view, the Documents band), `version-kpis` and `five-minute-demo`. They type-check and lint.

The seams were not confirmed with a human (none was available), so the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | Conversations: the list with Agent, Version and date filters and a Visitors/Playground/Both `Segmented`, `Pagination`, and the selected transcript beside it | Tests: "the list stays beside the transcript…", "Visitors, Playground or Both is a segmented choice", "a long list pages with Pagination", and `ConversationsTab.test.tsx`'s filter tests. Screenshots `conversations-*`, `conversation-visitor-*`, `conversations-paged-*`. |
| 2 | Transcripts badge guardrail blocks, show the answering Version, rating and feedback, and fold the Trace under each answer | Test: "a transcript badges each answer's Version, a Guardrail block, and folds the Trace under the answer", and the feedback and rating tests. Screenshots `conversation-visitor-*` (third answer blocked), `conversation-trace-*`, `conversation-playground-*`. |
| 3 | The Agent's Conversations view is the same list filtered to that Agent | Tests: "the Agent's Conversations view is the same list, filtered to that Agent", "…keeps its filters in the URL, without the Agent", "an Agent page's Conversations view lists that Agent's Conversations". Screenshots `agent-conversations-*`, `agent-conversation-*`. |
| 4 | Analytics: KPI cards with 95% intervals and n, low samples drawn dashed with a Low sample badge | Test: "KPI cards with a small sample carry a Low sample badge, with the interval and n", and `AnalyticsTab.test.tsx`'s card texts. Screenshots `analytics-*` (v2, small) and `analytics-enough-evidence-*`. |
| 5 | Analytics stays a Project section with an Agent filter; each Agent's views offer an "Analytics for this Agent" link that opens it pre-filtered | Tests: "Analytics takes its Agent from the URL…", "each Agent view offers Analytics for this Agent, opening it pre-filtered" (the section crumb stays Analytics). Screenshot `agent-versions-analytics-link-*`. |
| 6 | The chart uses `chart-1`, a 2px line with area fill, Live markers as labelled dashed rules, the Documents-changed band and note, a crosshair tooltip, and a Table view; never two y-axes | Tests: "the chart has a Table view…", "Live markers are labelled rules, and changed Documents draw a band with a note" (one `.recharts-yAxis`), "hovering the chart shows a crosshair readout…", and `TimeSeriesChart.test.tsx`. Colours aren't asserted in tests (the spec's rule): see `analytics-*`, `analytics-readout-*`, `analytics-table-*`. |
| 7 | Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR | The moved-actions table above (and in the PR). No API calls or permissions changed. All Studio tests pass. |
| 8 | The palette ratchet baseline is lowered to the new count | 19 → **15** (`frontend/palette-baseline.json`; [frontend-tests.log](frontend-tests.log)): the comparison's `bg-amber-50` and the old Conversations and Trace drawer classes are gone. |
| 9 | Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas | [screenshots/](screenshots/): 13 views, each `-light`, `-dark` (system) and `-chosen-dark`. Layout follows `docs/design/README.md` (*Pages*: Conversations, Analytics; the new *Charts* pattern). |
| 10 | axe reports zero AA violations on the changed pages in both Appearances | [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`, every view × 3 Appearances, **0 violations**. |
| 11 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams above; coverage in [frontend-tests.log](frontend-tests.log): 100% statements, branches, functions and lines. |
| 12 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | **Table view** added; **Low confidence** becomes **Low sample** (the old label under _Avoid_); **Conversations viewer**, **Agent view**, **Trace**, **Tombstone**, **Time series**, **Live History marker**, **Confounder note** and **Version KPIs** updated. No ADR decision changed (ADR-0013 already sets `chart-1` for data). |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `e469dc0`, which contains the latest `origin/candidate-reskin` (`cd2398c`). Each log's first line names its command and commit. GitHub Actions is down, so these are local.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 78 files, **1032 tests**, 100% statements (4531/4531), branches (3207/3207), functions (1635/1635) and lines (3964/3964). `embed.js` is 0.78 kB gzipped. 15 palette-class uses (baseline 15). | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Screenshots and axe | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 39 screenshots (13 views × 3 Appearances), 0 axe violations. | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack.** There is no Docker daemon here, so the backend, the 8 updated Playwright specs and `e2e/harness/axe.spec.ts` against the stack were not run. The specs type-check and lint. [shots.test.ts](shots.test.ts) stands in for the axe run: it serves the built Studio, answers the API with the unit tests' MSW fakes, and runs the same axe tags.
- **Blocked replies are inferred.** The Conversation API gives no Guardrail outcomes per Message, so a reply that named no model and isn't the fallback is badged as blocked: that is how the runtime records the input Guardrail's refusal (`playground/service.py`, "a fallback reply or a refusal asked no model"). Adding the outcomes to the API is a backend change this spec leaves out.
- **The Documents band covers the whole range.** The time series API counts Document changes for the range, not per day, so the band spans the plot; the note says so in words. Per-day changes would need the API.
- **Fixed chart width.** The chart is 720px wide and scrolls on narrow screens; narrow screens are 11-13's.
- **No pixel comparison.** The design canvas could not be opened from this sandbox; the comparison is against `docs/design/README.md` and the patterns.
