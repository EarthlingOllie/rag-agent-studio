# Evidence: ticket 13-10, Agentic answers stream word by word

Branch `t/13-10`, from `bcf109e9`: all of spec 12 plus spec 13 merged. The claim commit `68236052` set Status `in-progress`. The change is in commits `c2cc16fc` to `778dc6fd`, and the evidence logs are in `eb823005`. Every check below ran on that code. Afterwards only this folder and the ticket file were written.

**Status: done.** Every criterion is met and backed by the evidence below.

## What was built

- **Retraction event** (`backend/app/runtime/runtime.py`): `RetractEvent`, a frozen dataclass with no fields. Both streams send it as the SSE event `retract` with data `{}`. These are the Playground stream (`backend/app/playground/api.py`), the widget stream (`backend/app/embed/api.py`) and the Attack panel's demo stream (`backend/app/seed/attack_panel.py`). It is a new event, not the canary `ReplaceEvent`, so a Retraction records and shows no Guardrail outcome.
- **Streaming in Agentic mode**: `_stream_answer` no longer holds each response's text (the `held` list is gone). Text is yielded as it arrives, as in Automatic mode. When a response ends with a tool call, its text moves to `_Streamed.retracted` and the answer's text and labels are reset. If the response wrote any text, the `RETRACTION` marker is yielded before the tool runs, which is before that Search's `search` event.
- **What `_turn` does on a Retraction**: it calls `CanaryFilter.retract()` (new), which drops the held-back tail so it is never released. It yields `RetractEvent` only if something of the response was actually shown. A remark short enough to stay inside the filter's held tail is dropped silently. The saved answer, the `done` payload, the Trace and the Citations come from the answer's own text and labels only. A Chunk label that appears only in retracted text is never cited. Token usage still counts every model call, as before: the tokens were spent.
- **Canary**: every streamed piece of every response, retracted or not, is fed through the reply's one `CanaryFilter`. If the canary starts to appear, the model is stopped and a `ReplaceEvent` is sent, with the same `canary/leak/replaced` Guardrail outcome as in Automatic mode. After a retraction the filter checks the next response afresh, so a canary split between retracted text and the answer is not joined across the retraction. The post-completion `encoded_leak` check now covers the retracted texts as well as the answer. The search-query canary check is unchanged.
- **Fallback Text**: when the reply has searched, each Search's results are known before the next response streams. So `_turn` decides at that response's first piece: if no Search reached the Minimum Score, the Fallback Text is sent as the only `token`, and none of the model's text follows it (it is still fed to the canary filter). If that response then searches again, the Fallback Text is retracted like any other text. If the model's answer is empty, the Fallback Text is sent at the end, as before.
- **Clients**:
  - **Playground** (`frontend/apps/studio/src/projects/agents.ts`, `AgentPage.tsx`): `askPlayground` takes an `onRetract` that clears the answer's content. The "Searching: …" lines stay.
  - **Widget** (`frontend/apps/widget/src/chat.ts`, `Widget.tsx`): `onRetract` clears the reply's text and sets `searching`, which shows the existing searching status row. That row is announced once per reply through the polite live region. Retracted text is never announced, because the Reply announcement is the final answer. The widget's `search` event carries no data, so the model's query never reaches it.
  - **Attack panel demo page** (`frontend/apps/widget/host/demo/attacks.html`): it clears its stream on `retract`.
  - **Attack eval runner** (`backend/app/evals/runner.py`): retracted text is not the reply, but it still counts when the runner checks for a marker the Visitor saw.
- **API client**: the `retract` event appears in the OpenAPI descriptions of both streams. `openapi.json` and `schema.gen.ts` are regenerated, and `make check-client` passes.
- **Docs**:
  - The spec's runtime section and Further Notes are updated (`docs/specs/13-agentic-retrieval-spec.md`), and the ticket is linked in its ticket list.
  - The runtime module docstring and the Playground and embed API docstrings describe the `retract` event.
  - ADR-0015's Fallback Text consequence is updated.
  - `GLOSSARY.md` gains **Retraction**.
  - 13-02's evidence README notes that 13-10 supersedes its hold.
  - The ticket is listed in `docs/tickets/README.md`.

## Test seams

These are the pre-agreed [shared test seams](../../../specs/README.md#shared-test-seams). No human was available to confirm new seams, and no new seam was added.

- **API seam** (`backend/tests/integration/test_agentic_streaming.py`, new). Scripted `FunctionModel`s from `app/gateway/fakes.py` run against real Postgres and Redis through the Draft, Playground and widget HTTP APIs. Each test reads the SSE stream, the saved Conversation and the Trace.
  - `test_an_agentic_answer_streams_word_by_word`, `test_an_agentic_answer_streams_in_pieces_then_cites`: the answer arrives in several `token` events.
  - `test_text_written_before_a_search_streams_then_is_retracted_and_never_kept`: a text-then-tool-call response. The stream is `token`… `retract` `search` `token`… `done`, and the retracted text appears in no saved message, `done` payload or Trace.
  - `test_a_remark_too_short_to_leave_the_canary_filter_is_dropped_with_no_retraction`
  - `test_text_before_each_of_several_searches_is_retracted_and_its_labels_never_cited`: multi-search. A label written only in retracted text is not cited.
  - `test_text_the_canary_filter_held_back_is_dropped_on_a_retraction`: the filter's tail is never released after a retraction.
  - `test_a_canary_in_text_before_a_search_cuts_the_reply_off_and_replaces_it`: canary in pre-search text. The result is `replace`, the Guardrail outcome is recorded, and no Search runs.
  - `test_a_canary_straddling_chunks_of_the_answer_after_a_search_is_replaced`
  - `test_a_canary_split_between_retracted_text_and_the_answer_is_not_a_leak`: no false positive across a retraction.
  - `test_an_encoded_canary_in_retracted_text_is_flagged`
  - `test_searched_and_found_nothing_sends_the_fallback_text_and_no_answer_token`: the only `token` is the Fallback Text, with zero answer tokens.
  - `test_found_nothing_and_answered_nothing_still_gives_the_fallback_text`
  - `test_the_fallback_text_is_retracted_when_the_model_searches_again_and_finds`
  - `test_a_canary_in_the_answer_hidden_behind_the_fallback_text_still_replaces_it`
  - `test_a_visitor_gets_the_retraction_and_never_the_query`: on the widget stream, `retract` has data `{}` and `search` has no query.
- **Existing API tests updated**:
  - `test_agentic_retrieval.py::test_text_the_model_writes_before_searching_is_retracted_and_kept_out_of_the_answer`: it previously asserted the hold.
  - `test_attack_panel.py::test_an_agentic_guardrail_demo_agent_retracts_what_it_wrote_before_searching`
- **Attack eval runner** (`tests/unit/test_attack_eval_runner.py::test_a_marker_shown_before_a_retraction_still_counts_but_is_not_the_reply`)
- **Frontend unit tests** (Vitest + Testing Library + MSW):
  - `frontend/apps/studio/src/projects/AgentPage.test.tsx`: "text the model streamed before searching is cleared, then the Search shows and the answer streams".
  - `frontend/apps/widget/src/Accessibility.test.tsx`: "text streamed before a Search is retracted: the reply shows the searching status again, and only the answer is announced". The text is cleared and the status row shows. The status is announced once, even after a second retraction in the same reply. The announcement holds the answer alone.
- **End-to-end specs** (updated; lint, typecheck and `pnpm e2e --list` pass; not run here). The integrated run must cover:
  - `frontend/e2e/tests/playground.spec.ts`: the Agentic Playground test injects text and `retract` before the first `search` and asserts it is cleared.
  - `frontend/e2e/tests/widget-accessibility.spec.ts`: retracted text gives way to the searching status, which is announced once, and the retracted text is never in the answer or the announcement.
  - `frontend/e2e/tests/attack-panel.spec.ts`: "text retracted before a Search is cleared from the reply".

## Acceptance criteria and requirements

| # | Criterion (ticket) / requirement (product owner) | Evidence |
|---|---|---|
| 1 | Agentic text streams as it arrives; nothing holds it (req. 1) | `_stream_answer` without `held`; `test_an_agentic_answer_streams_word_by_word`, `…_in_pieces_then_cites` |
| 2 | `RetractEvent`, SSE `retract` (no data), before the Search's `search`; no Guardrail outcome (req. 2) | `RetractEvent`; `test_text_written_before_a_search_streams_then_is_retracted_and_never_kept`, `test_a_visitor_gets_the_retraction_and_never_the_query`, `test_an_agentic_guardrail_demo_agent_retracts_what_it_wrote_before_searching` |
| 3 | Retracted text never in saved reply, Trace, `done` or Citations (req. 2) | the same tests; `test_text_before_each_of_several_searches_is_retracted_and_its_labels_never_cited`; `test_a_marker_shown_before_a_retraction_still_counts_but_is_not_the_reply` |
| 4 | Canary over every response, straddling chunks, held tail dropped on Retraction, encoded canary in retracted text flagged, query check unchanged (req. 3) | `test_a_canary_in_text_before_a_search_cuts_the_reply_off_and_replaces_it`, `test_a_canary_straddling_chunks_of_the_answer_after_a_search_is_replaced`, `test_text_the_canary_filter_held_back_is_dropped_on_a_retraction`, `test_a_canary_split_between_retracted_text_and_the_answer_is_not_a_leak`, `test_an_encoded_canary_in_retracted_text_is_flagged`, `test_a_canary_in_the_answer_hidden_behind_the_fallback_text_still_replaces_it`; 13-07's `test_agentic_guardrails.py` still passes |
| 5 | Fallback Text decided as the next response starts, zero answer tokens first; retracted if that response searches (req. 4) | `test_searched_and_found_nothing_sends_the_fallback_text_and_no_answer_token`, `test_found_nothing_and_answered_nothing_still_gives_the_fallback_text`, `test_the_fallback_text_is_retracted_when_the_model_searches_again_and_finds`; 13-04's tests still pass |
| 6 | Playground clears retracted text, keeps "Searching: …" (req. 5) | `AgentPage.test.tsx` retraction test; `playground.spec.ts` |
| 7 | Widget clears, shows searching status, announces once, never announces retracted text, never shows the query (req. 5) | `Accessibility.test.tsx` retraction test; `test_a_visitor_gets_the_retraction_and_never_the_query`; `widget-accessibility.spec.ts` |
| 8 | `retract` documented in OpenAPI and docstrings; `make check-client` passes (req. 5) | [check-client-and-links.log](check-client-and-links.log): "API client is up to date.", exit 0 |
| 9 | Spec, runtime docstring, ADR-0015 updated; 13-02 evidence notes the supersession (req. 6) | see Docs above; `make link-check` exit 0 in [check-client-and-links.log](check-client-and-links.log) |
| 10 | E2e specs for Playground, widget, Attack panel cover it and lint, typecheck, list | [e2e-list.log](e2e-list.log) (122 tests in 65 files, exit 0); lint and typecheck in [frontend-checks.log](frontend-checks.log) |
| 11 | New Studio UI uses the design system; palette ratchet passes | The only Studio change is clearing content in an existing component, with no new markup or classes. The palette ratchet passes in [frontend-checks.log](frontend-checks.log). |
| 12 | Tests at the highest seam; 100% line and branch coverage | Seams above; [backend-tests.log](backend-tests.log); frontend 100% statements, branches, functions and lines in [frontend-checks.log](frontend-checks.log) |
| 13 | Glossary and ADRs current (req. 6) | `GLOSSARY.md` **Retraction**; ADR-0015 |

## Results

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `cd backend && TEST_DATABASE_URL=…/studio_test_t10 TEST_REDIS_URL=redis://localhost:6379/15 uv run pytest -n 3` | BACKEND_RESULT | [backend-tests.log](backend-tests.log) |
| Backend lint and types | `make lint-backend` (ruff check, ruff format --check, mypy) | exit 0 | [lint-backend.log](lint-backend.log) |
| API client drift and links | `make check-client`, `make link-check` | up to date; all links resolve; exit 0 | [check-client-and-links.log](check-client-and-links.log) |
| Frontend | `pnpm test && pnpm check-embed-size && pnpm palette-ratchet && pnpm lint && pnpm typecheck` | 1114 tests passed in 85 files; coverage 100% (statements, branches, functions, lines); embed size, ratchet, lint and typecheck pass | [frontend-checks.log](frontend-checks.log) |
| E2e listing | `pnpm e2e --list` | 122 tests in 65 files, exit 0 | [e2e-list.log](e2e-list.log) |

## Gaps

- The Playwright stack was not run here, as instructed. The integrated run must cover `playground.spec.ts`, `widget-accessibility.spec.ts` and `attack-panel.spec.ts`.
