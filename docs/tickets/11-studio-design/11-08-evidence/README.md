# Evidence: ticket 11-08, Agent page and its four views

Branch `ticket/11-08-agent-views`, from `origin/candidate-reskin` at `034a445` (the merge of 11-05, #86). The claim commit `f1f513d` set Status `in-progress`. Then:

- `0b7dd02` adds `TopBarActions` (a slot in the top bar for a page's own actions), teaches the navigation helpers the "Agents" and "Agent views" switchers, and adds the Playwright helpers for the Agent views (`e2e/fixtures/agent.ts`).
- `1e4a8f2` is the Agent page: the Agent and view switchers, the three routed views, the top bar actions, the ⋯ menus and their confirmations, the badges. It also updates the unit tests and 18 end-to-end specs.
- `4158129` adds **Agent view** to `GLOSSARY.md` and updates `docs/design/README.md` and the `studio-reskin` patterns.
- `d89e978` merges `origin/candidate-reskin` (`0b65fe4`: 11-11, 11-12 and the reskin screenshots). The one conflict was the **Breadcrumb** glossary entry, which now names both tickets' switchers.
- `001392b` gives the Trace's table cells some room. `b1d24d2` is this folder's scripts, and `e17d6fd` the first evidence run.
- `31f8df7` merges `origin/candidate-reskin` `66663ff` (11-06): the breadcrumb now has both the Document crumb and the Agent crumbs, and the design README both pages. `a03ce0d` drops `TextDiff`, unused once 11-07's Instructions Versions show the design `Diff`. `34bc17b` merges `358bfd0` (11-07, 11-09): the Agents list is 11-09's table, so the specs read it, and reach it through the section switcher.
- The last commit changes only this folder (the logs and screenshots of the run at `34bc17b`).

No backend code, API call or permission changes. Three routes are added under the Agent (below).

**Status: done.** Every criterion is met and evidenced below. Gaps are listed at the end.

## What was built

**The breadcrumb inside an Agent** (`shell/StudioBreadcrumb.tsx`, `AgentBreadcrumb`):

`Analytical Engines / Projects ▾ / HR handbook ▾ / Agents ▾ / HR helper ▾ / **Playground ▾**`

- **Agent switcher**, "<Agent>, Agents": the Project's open Agents as router links to their Playground, the open one current. An archived Agent is opened from the Agents list, as Projects are.
- **View switcher**, "<view>, Agent views", the current crumb: Playground (`/agents/<id>`), Versions (`/agents/<id>/versions`), Embed & limits (`/agents/<id>/embed`) and Conversations (the Project's Conversations with `?agent=<id>`, the link that was at the foot of the Agent page).
- The Agents section crumb is now an ancestor. Until the Agent loads, or when it can't be found, the section crumb stays current and there are no Agent crumbs.

**The top bar** (`AgentTopBar`, through `TopBarActions`): the Draft's **Saved state** ("All changes saved", "Unsaved changes", "Saving…", "Read only while archived."… as `role="status"` "Draft status", shown while the Playground view's editor is open), **History** (a link to the Versions view) and **Publish** (`button.primary`; it opens a `Dialog` "Publish <Agent>" with the publish form and its diff). An archived Agent has no Publish.

**The header** (`AgentHeader`): the name, then `Badge`s: **Live** with the **Version** chip (`v2`, read as "Version 2"), or **Not live**; **Draft** while the Draft has unpublished changes (titled "The Draft has changes that aren't published yet."); **Budget spent**; Block rate spike. Then a ⋯ button "More Agent actions" (menu "Agent actions"):

| Agent | ⋯ menu |
| --- | --- |
| Active, live, Draft changed | Discard Draft, Archive |
| Active otherwise | Archive |
| Archived, Owner | Delete permanently (danger) |
| Archived, Editor | no ⋯ button: nothing to offer |

Each confirms in a destructive `ConfirmDialog` ("Discard the Draft?", "Archive HR helper?", "Delete Old helper permanently" with the typed name in its body; Enter confirms once the name matches). A refused discard or archive shows the API's reason under the header. Restore stays in the archived notice.

**Playground view** (`AgentPlaygroundView`): the Playground in the main column (max 720px, centred) and the configuration beside it (360–420px), wrapping under it on narrow screens.

- Messages: the question as a bubble on the right; the answer beside an avatar, at 16px, with its citation chips (the label in the accent colour).
- The **Trace folds under each answer** (`TraceFold`, a `<details>` card named "Trace"): its summary row shows the usage in mono; opening it loads the Trace once. Cited chunks are in the accent colour and chunks the ingestion scan flagged in the flag colour. It replaces the Trace drawer here; Conversations keep the drawer until 11-10.
- The Instructions picker and Reset conversation sit above the messages; the composer is a pill with the question field and Send.
- **Configuration** (`DraftEditor`): Behaviour, Retrieval, Experience and Guardrails as `Section`s with mono summaries ("Default Model · temp 0.7", "top-5 · hybrid 0.5", "0 starter questions", "block · fail closed"). Behaviour is open and the others folded; a section opens by itself when the API refuses one of its settings. Each section's controls are a `fieldset` named after it, so it can still be disabled as a whole. The markdown editor for the system prompt is unchanged.
- An archived Agent shows "The Playground is off while the Agent is archived." and its read-only configuration.

**Versions view** (`AgentVersionsView`):

- **Live History** as a timeline: a rail with a dot per change, the Live Version's in the accent colour. The Live Version's entry has a ⋯ "Actions for the Live Version" with **Revert to v<n>**, confirmed in a `ConfirmDialog` "Revert to v<n>?". When there is nothing to revert to, that is said, as before.
- **Versions**: each with its Version chip, the Live badge, note, author, time and pinned Instructions, and a ⋯ "Actions for v<n>" with **Start Draft from v<n>**, confirmed in a `ConfirmDialog` "Start Draft from v<n>?". An archived Agent's Versions have no ⋯.
- **Compare**: From and To pickers, then each changed setting. Markdown changes (the system prompt) and the pinned Project Instructions are the design system's `Diff` (line numbers, + and −, soft green and soft red). The publish dialog and Analytics' comparison use the same view.

**Embed & limits view** (`AgentEmbedView`), as cards:

- **Embed Snippet**: the Launcher choice (and the container selector for inline), then a `CodeBlock` with Copy ("Copy Embed Snippet").
- A note that Operational Settings apply at once, without publishing.
- **Allowed Origins**: an `EditableList` (Enter or Add adds; each has Remove), warning "No site can embed this Agent until you add an origin." when empty, and **Save Allowed Origins**. The API still validates and normalises each origin.
- **Unavailable text**, **Token Budget** (a `Meter` "Tokens used today" with the value printed, the percentage line and the spent explanation, then Tokens per day) and **Rate limits**.
- **Theme override** (was "Widget branding"): colours and avatar; Owners change it, Editors see it.
- An archived Agent's view says "An archived Agent can't be embedded. An Owner can restore it.", as the page used to leave these out.

### Moved actions (behaviour otherwise unchanged)

| Before | After |
| --- | --- |
| "All Agents" link above the Agent | The Agents section crumb, or the Agent switcher |
| (none) | Agent switcher: jump straight to another open Agent |
| "Conversations with this Agent" link at the foot of the page | View switcher → Conversations (the same filtered link) |
| One long page: Draft, Playground, Publish, Embed, branding, Live History, Versions | Views: Playground (Playground + configuration), Versions (Live History, Versions, Compare), Embed & limits (snippet, Operational Settings, Theme override) |
| Draft status beside the Draft heading | Saved state in the top bar |
| Publish form on the page | Top bar Publish → the "Publish <Agent>" dialog (the same form and diff) |
| (none) | Top bar History → the Versions view |
| "Archive Agent" button, then an inline "Yes, archive …" panel | ⋯ → Archive, then the "Archive …?" `ConfirmDialog` (confirm still "Yes, archive …") |
| "Delete permanently" in the archived notice, then an inline form | ⋯ → Delete permanently, then the "Delete … permanently" `ConfirmDialog` with the name field |
| "Discard Draft" button, then an inline panel | ⋯ → Discard Draft, then the "Discard the Draft?" `ConfirmDialog` (confirm still "Yes, discard the changes") |
| "Revert to v<n>" button, then an inline panel | Live Version's ⋯ → Revert to v<n>, then the "Revert to v<n>?" `ConfirmDialog` (confirm still "Yes, revert to v<n>") |
| "Start Draft from v<n>" link per Version, then an inline panel | That Version's ⋯ → Start Draft from v<n>, then the `ConfirmDialog` (confirm still "Yes, replace the Draft") |
| "Trace" button opening a drawer | The Trace folds open under the answer |
| Allowed Origins as a one-per-line textarea | An `EditableList`, warning when empty |
| Token Budget progress bar | `Meter` |
| "Live v3", "Not live", "Unpublished changes", "Budget exhausted" pills | `Badge`s: Live + v3, Not live, Draft, Budget spent (the Agents list shows them too) |
| "Widget branding" section | "Theme override" card in Embed & limits |
| "Loading the Agent…" text; "The Agent could not be found." | `Skeleton` "Loading the Agent"; `EmptyState` "Agent not found" with All Agents |

API calls, permissions and the Agents list's other content are unchanged.

## Test seams

The spec's frontend seams:

- **Network seam:** `renderStudio` with MSW, at the Agent's URLs.
  - `projects/AgentViews.test.tsx` (new, 20 tests) covers the Agent switcher (open Agents, current, switching), the view switcher (order, `href`s, current view, switching), an Agent that can't be listed or found, the top bar's Saved state, History and Publish (and none for an archived Agent), the badges, the configuration sections (open, folded, summaries, opening on a refused setting), the folded Trace, the ⋯ menu's Archive, Delete permanently and Discard Draft, Revert and Start Draft from in their ⋯ menus, the Diff in Compare, and the Embed & limits cards (CodeBlock, EditableList and its warning, Meter, the archived message).
  - The existing Agent tests (`AgentPage`, `AgentArchive`, `AgentDrafts`, `AgentEmbed`, `AgentLiveHistory`, `AgentPublish`, `AgentBranding`, `PlaygroundInstructions`, `DraftEditor`, `AgentsTab`, `ConversationsTab`, `AnalyticsTab`) now go through the views, the menus and the dialogs, with the same assertions on behaviour.

  The new tests were written red first: 18 of the 19 failed against the old page (the one that passed, a section opening on a refused setting, passed only because nothing folded yet).
- **Component seam:** `shell/TopBarActions.test.tsx` covers the slot outside the shell.
- **End-to-end seam:** 18 specs are updated but were not run (no stack): `agent-archive`, `agent-config`, `agent-drafts`, `agent-publish`, `agent-revert`, `branded-widget`, `conversations`, `demo-pages`, `embed`, `five-minute-demo`, `llm-classifier`, `operational-settings`, `playground`, `playground-instructions`, `rate-limits`, `reranker`, `tag-scoping` and `token-budget`. They use the new helpers in `e2e/fixtures/agent.ts` (`openAgentView`, `agentAction`, `openSettings`, `publishAgent`, `saveAllowedOrigins`, `liveVersion`).

The seams were not confirmed with a human (none was available), so the spec's own seams were used.

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | The Agent crumb switches Agent; a view crumb switches between Playground, Versions, Embed & limits and Conversations | Tests: "the Agent crumb lists the Project's open Agents and switches between them" and "the view crumb switches between Playground, Versions, Embed & limits and Conversations". Screenshots `menu-agents-*`, `menu-agent-views-*`. |
| 2 | Saved state, History and Publish sit in the top bar; Live, Draft and Not live use `Badge` | Tests: "Saved state, History and Publish sit in the top bar", "the top bar's Saved state follows the Draft as it is edited", "an archived Agent has no Publish…", "Live, Draft and Not live are badges beside the Agent's name". Screenshots `agent-playground-*`, `agent-not-live-*`, `dialog-publish-*`. |
| 3 | Playground: messages in a centred column, the Trace folded under each answer (cited chunk in the accent colour, flagged chunks in the flag colour), the Instructions picker and composer restyled | `Playground` and `TraceFold`. Test: "each answer's Trace folds open under it", and the Trace tests in `AgentPage.test.tsx` and `PlaygroundInstructions.test.tsx`. Colours are not asserted in tests (the spec's rule); see `agent-playground-trace-*` (C1 "Cited" in the accent). |
| 4 | Configuration: Behaviour, Retrieval, Experience and Guardrails as `Section`s with mono summaries; the markdown editor keeps working | Tests: "the configuration is four sections…", "a section opens to show a setting the API refused", and the `DraftEditor.test.tsx` tests (the system prompt included). Screenshots `agent-playground-*`, `agent-configuration-open-*`. |
| 5 | Versions: Live History as a timeline, From/To picking, `Diff` for Instructions and settings, Revert and Start Draft from in ⋯ menus | Tests: "Versions: Revert and Start Draft from are in ⋯ menus…", "Versions compares From and To with a line Diff…", and `AgentLiveHistory.test.tsx`, `AgentDrafts.test.tsx`. Screenshots `agent-versions-*`, `confirm-revert-*`, `confirm-start-draft-*`. |
| 6 | Embed & limits: `CodeBlock` snippet with launcher choice, Allowed Origins as an `EditableList` warning when empty, Unavailable text, Token Budget `Meter` and rate limits, Theme override for Owners | Tests: the three "Embed & limits:" tests and `AgentEmbed.test.tsx`, `AgentBranding.test.tsx` (Editors see it but can't change it). Screenshots `agent-embed-*`, `agent-archived-embed-*`. |
| 7 | Archive and delete use the ⋯ menu and `ConfirmDialog` | Tests: "the Agent's ⋯ menu archives it after a confirmation", "an archived Agent's ⋯ menu deletes it permanently once its name is typed", and `AgentArchive.test.tsx`. Screenshots `menu-agent-actions-*`, `confirm-archive-*`, `confirm-delete-*`, `confirm-discard-*`. |
| 8 | Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR | The moved-actions table is above and in the PR. No API calls or permissions changed. All Studio tests pass (counts below). |
| 9 | The palette ratchet baseline is lowered to the new count | The count is **19** (11-06, 11-07 and 11-09 lowered it from 24 on the base), and the baseline equals it ([frontend-tests.log](frontend-tests.log)). This ticket adds none: the Agent page had no palette classes left after 11-03 and the new code uses tokens and recipes only. The two matches in `AgentBranding.tsx` are the words `dark:` in an object (a colour's light and dark values), not classes. |
| 10 | Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas | [screenshots/](screenshots/): 17 views, each `-light`, `-dark` (system) and `-chosen-dark`. The layout follows the design README's *Agent page* and the `studio-reskin` R4 pattern: the Playground's centred column, the configuration panel of `Section`s, the folded Trace, the top bar actions. |
| 11 | axe reports zero AA violations on the changed pages in both Appearances | [shots-axe.log](shots-axe.log): tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` and `wcag22aa`, on every view above × 3 Appearances, **0 violations**. |
| 12 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams are above. Coverage is in [frontend-tests.log](frontend-tests.log): 100% statements (4470/4470), branches (3156/3156), functions (1620/1620) and lines (3904/3904). |
| 13 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | **Agent view** added, and **Breadcrumb** names the Agent and view switchers. No ADR decision changed: ADR-0013 already says navigation is the breadcrumb, and the spec signed off the views as a crumb. |

## Results

[run-checks.sh](run-checks.sh) ran these in the ticket's worktree at `34bc17b`, which contains the latest `origin/candidate-reskin` (`358bfd0`). Each log's first line names its command and commit. GitHub Actions is down, so these are local.

| Check | Command | Result | Log |
| --- | --- | --- | --- |
| Install | `pnpm install --frozen-lockfile` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint-frontend` (eslint, tsc, e2e included) | exit 0 | [lint.log](lint.log) |
| Tests, coverage, embed budget, ratchet | `make test-frontend` | exit 0. 77 files, **1019 tests**, 100% statements, branches, functions and lines. `embed.js` is 0.78 kB gzipped. 19 palette-class uses (baseline 19). | [frontend-tests.log](frontend-tests.log) |
| Build | `pnpm build` | exit 0 | [build.log](build.log) |
| Link check | `make link-check` | exit 0 | [link-check.log](link-check.log) |
| Playwright harness | `pnpm e2e:harness` (Chrome) | exit 1: 12 passed, 2 failed. The two failures are the tab-row tests of `e2e/harness/navigation.spec.ts`, which fail the same way on `origin/candidate-reskin` `358bfd0`: 11-11 emptied `TAB_ROWS` (no tab row is left) but the spec still opens one. This ticket does not touch that spec. Not part of the merge gate. | [e2e-harness.log](e2e-harness.log) |
| Screenshots and axe | [shots.test.ts](shots.test.ts) via [shots.config.mjs](shots.config.mjs) (the built Studio in Chrome) | exit 0. 51 screenshots (17 views × 3 Appearances), 0 axe violations. | [shots.log](shots.log), [shots-axe.log](shots-axe.log) |

## Gaps

- **No compose stack.** There is no Docker daemon in this sandbox, so the backend, the 18 updated Playwright specs and `e2e/harness/axe.spec.ts` against the stack were not run. The specs type-check and lint. [shots.test.ts](shots.test.ts) stands in for the axe run: it serves the built Studio, answers the API with the unit tests' MSW fakes, and runs the same axe tags.
- **Conversations view in place.** The view switcher's Conversations opens the Project's Conversations filtered to the Agent (the link the page had). Showing the list inside the Agent, with its pill filters, is 11-10's.
- **Full bleed.** The Agent page stays inside `layout.page`; the two columns wrap rather than filling the window. The narrow-screen top bar is 11-13's.
- **Switching views starts a new Playground chat.** The views are routes, so the Playground's messages are not kept when the Member opens Versions and comes back (its Conversation is recorded as before).
- **No pixel comparison.** The design canvas could not be opened from this sandbox. The comparison is against `docs/design/README.md` and the patterns.
- **Harness tab-row tests** fail on the base too (see Results); whoever next touches the navigation helpers should drop them.
