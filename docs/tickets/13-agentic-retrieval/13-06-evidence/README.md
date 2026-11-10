# Evidence: ticket 13-06, Widget searching status and Token Budget

Branch `t/13-06`, from `0823a537` (all of spec 12, plus merged `t/13-01` and `t/13-02`). The change is commit `89d09d00` (the feature), `a8bfb5e3` (widget test: the override shows in the reply row) and `f6a4f8b4` (attack panel test; it closes a coverage gap `89d09d00` opened). A container restart interrupted the first job after `89d09d00`; this run reviewed that commit, kept it, and finished the checks below at `f6a4f8b4`. Only this folder and the ticket file were written afterwards.

**Status: done.** Every criterion is met and evidenced below. The end-to-end specs are updated, lint, typecheck and list, but were not run here (see "End-to-end").

## What was built

- **Widget SSE** (`backend/app/embed/api.py`): `answer(..., searches=True)`; each `SearchEvent` becomes `event: search` with data `{}`. The model's query never leaves the server. The OpenAPI description of the messages endpoint says so.
- **UI text override** (`backend/app/agents/config.py`): `UiText.searching_status` (ShortText, optional; none keeps "Searching the knowledge base…"). Client regenerated (`frontend/packages/api-client`). Studio Experience editor gains a "Searching status" field (`DraftEditor.tsx`, design-system `TextField`).
- **Widget** (`frontend/apps/widget/src/{chat.ts,Widget.tsx,styles.ts}`): `onSearch` handler; the pending reply shows a `.searching` row with the override or the built-in text until its first token; the first `search` of a reply puts the status in the existing polite `Announcements` live region once (later Searches in the same reply announce nothing more; the next reply announces again). Embed loader size unchanged (`embed.js` 1367 B, 778 B gzipped).
- **Token Budget**: no code change was needed. 13-02 made `DoneEvent` usage the run's summed `RunUsage`, and the widget path already adds it to the Agent's counter; the Playground path never does. Tests pin both for Agentic replies.
- **Attack panel** (`backend/app/seed/attack_panel.py`, unchanged): it is the one `answer()` caller left without `searches`, so an Agentic Guardrail demo Agent's Searches are dropped before its `trace` event. A new test pins it.

## Test seams

The [shared test seams](../../../specs/README.md#shared-test-seams). No human was available to confirm seams, so these are the pre-agreed ones.

- **API seam** (real Postgres and Redis, scripted `FunctionModel`):
  - `test_agentic_retrieval.py::test_a_visitor_is_told_of_each_search_but_never_sees_its_query`: two Searches give two `("search", {})` events before `token`, `citation`, `done`; neither query appears anywhere in the response.
  - `test_agentic_retrieval.py::test_an_agentic_reply_spends_every_token_it_used_of_the_budget_and_the_playground_none`: a Playground answer leaves `tokens_used` at 0; one Visitor reply (two model calls) adds 109 (2 x 50 input, 5 + 4 output).
  - `test_agent_config.py` / `test_branded_widget.py`: `searching_status` round trip, trimming, 201 characters refused, default `None` in the boot payload.
  - `test_attack_panel.py::test_an_agentic_guardrail_demo_agent_searches_but_the_panel_streams_no_search`: the panel streams `token`, `trace`, `done` only (fails with `'SearchEvent' object has no attribute 'event'` if `answer()` streams Searches to it).
- **Frontend network seam (MSW)** (`frontend/apps/widget/src`):
  - `Accessibility.test.tsx`: status row shown, announced once though three `search` events arrive, replaced by the first token, then the Reply announcement; each searching reply announces again (`["Searching…", "HR helper: Yes.", "Searching…", "HR helper: Yes."]`); the override is what the row shows and what is announced (verified red by reverting the row to the built-in text).
  - `Widget.test.tsx`: the override is announced and a stream that ends after a `search` gives way to the error alert.
  - Studio `DraftEditor.test.tsx`: the Searching status field saves `searching_status`.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Widget SSE gains a `search` event with no query | `embed/api.py`; `test_a_visitor_is_told_of_each_search_but_never_sees_its_query` |
| 2 | Searching status row while Searches run, replaced when the answer streams | `Widget.tsx`; `Accessibility.test.tsx` (first test) |
| 3 | Announced once per reply through the polite live region | `Accessibility.test.tsx` (first two tests) |
| 4 | `searching_status` override, used when set | `config.py`, `DraftEditor.tsx`, `Widget.tsx`; `test_agent_config.py`, override tests in `Accessibility.test.tsx` and `Widget.test.tsx`; [check-client-and-links.log](check-client-and-links.log) "API client is up to date." |
| 5 | Token Budget counts the reply's summed tokens; Playground exempt | `test_an_agentic_reply_spends_every_token_it_used_of_the_budget_and_the_playground_none` |
| 6 | axe covers the widget with the status showing | `frontend/e2e/tests/widget-accessibility.spec.ts` (Agentic Agent; the stream is held after the first `search` so axe runs while the status shows, light and dark); deferred to the integrated run |
| 7 | Tests at the highest seam; 100% line and branch coverage | Seams above; backend and frontend coverage below |
| 8 | Glossary / ADRs | `GLOSSARY.md`: new **Searching status**; **Token Budget** says usage is summed over every model call. No ADR decision changed. |

Standing criteria: Studio UI uses the design system (`TextField`, palette ratchet "0 palette-class uses"); widget styles are the widget's own (not Studio).

## Results

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage | `cd backend && TEST_DATABASE_URL=…/studio_test_t06 TEST_REDIS_URL=redis://localhost:6379/3 uv run pytest -n 3` | 2569 tests: 2564 passed, 5 failed under load (each passes alone, below); coverage **100.00%** (12212 statements, 1520 branches), gate reached | [backend-tests.summary.log](backend-tests.summary.log) |
| Backend lint and types | `make lint-backend` | exit 0 | [lint-backend.log](lint-backend.log) |
| Client drift, links | `make check-client`, `make link-check` | up to date; all links resolve | [check-client-and-links.log](check-client-and-links.log) |
| Frontend tests | `pnpm test` | 1093 passed, 84 files; 100% statements, branches, functions, lines | [frontend-checks.log](frontend-checks.log) |
| Frontend static | `pnpm check-embed-size && pnpm palette-ratchet && pnpm lint && pnpm typecheck` | exit 0 | [frontend-static-checks.log](frontend-static-checks.log) |
| e2e listing | `pnpm exec playwright test --list …` | 12 tests in 7 files list | [e2e-list.log](e2e-list.log) |

The first backend run ([backend-tests-run1.summary.log](backend-tests-run1.summary.log), at `89d09d00`, load average about 25 with four tickets sharing 4 CPUs) had 2564 passed and 4 failed: the four `test_logging.py` subprocess tests timed out waiting for uvicorn/celery to start; rerun alone they pass ([backend-test-logging-rerun.log](backend-test-logging-rerun.log), 8 passed). It also showed coverage 99.99%: `app/playground/service.py` 500->502, the path that drops SearchEvents for a caller that did not ask for them, lost its only test when the widget began asking. `f6a4f8b4` adds the attack-panel test that takes it ([backend-attack-panel-coverage.log](backend-attack-panel-coverage.log)).

The run at `f6a4f8b4` ([backend-tests.summary.log](backend-tests.summary.log)) reached the 100% coverage gate. Its five failures are load, not this change: the same four `test_logging.py` start-up timeouts, and `test_agent_versions.py::test_deleting_the_agent_or_erasing_the_organisation_removes_its_versions` (a foreign-key violation deleting the Agent; the test calls `answer()` directly with its default arguments and runs no Agentic Agent, so nothing in this ticket reaches it). Rerun alone, all nine pass, and the whole `test_agent_versions.py` passes, 28 tests ([backend-rerun-alone.log](backend-rerun-alone.log)). Two other full runs between these were killed by the kernel for lack of memory (four suites ran at once on the machine) and left no result.

## End-to-end (deferred to the integrated run)

The Playwright stack was not run in this job (shared machine). The integrated run must cover:

- `frontend/e2e/tests/widget-accessibility.spec.ts` (all three tests: axe with the searching status showing, light and dark; status text and its announcement)
- `frontend/e2e/tests/token-budget.spec.ts` (Agentic Agent; the widget stream starts with `event: search` / `data: {}`; budget spent by summed tokens; Playground still answers)
- Regression: `embed.spec.ts`, `branded-widget.spec.ts`, `widget-lifecycle.spec.ts`, `agent-config.spec.ts`, `playground.spec.ts`
