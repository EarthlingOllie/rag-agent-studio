# Evidence: ticket 13-04, Search limit and Fallback Text

Branch `t/13-04`, from `0823a537`: the integration branch with all of spec 12, plus merged `t/13-01` and `t/13-02`. The change was committed after a container restart interrupted the first run, and the evidence was added in the commit after it. This folder holds the logs from the checks run on it.

**Status: done.** Every criterion is met and evidenced below.

## What was built

- **Search limit** (`backend/app/runtime/runtime.py`, `_knowledge_search`): Searches are numbered as they start. When a call's number is past the Agent's `retrieval.search_limit`, it does not search. It returns `SEARCH_LIMIT_REACHED` ("search limit reached; answer from what you have", `app/runtime/prompt.py`) to the model, streams no `SearchEvent` and is recorded as a `Searched` with `limit_refused=True`. The model keeps running and answers from the Chunks it already has. The refused call is persisted as a Search row with `limit_refused` true, so the Trace lists it and shows that the limit was hit. `DoneEvent.search_count` counts only the Searches that actually ran (a refused call searched nothing). `messages.search_count` and the `done` SSE event use that count.
- **Agentic fallback** (`_found_nothing` in `runtime.py`): the reply searched, but no Search gave the model a Chunk (none reached the Minimum Score). The answer text only arrives after every Search has run, because 13-02 holds a tool-calling response's text until the response ends. So the first answer text is dropped before anything is sent, and the model stream is closed. The reply is then the Agent's Fallback Text with `fallback` true. It keeps the Searches and their excluded Chunks, and the tokens the model used. A reply that made no Search is never a fallback.
- **Persistence** (`backend/app/playground/service.py`): an Agentic fallback did ask the model, so it records the model name, its summed tokens and its Cost. The analytics count its tokens as for any reply that asked a model. An Automatic fallback and a refusal still name no model, as before.
- **Docs**: `GLOSSARY.md` "Search limit" now says that a refused call isn't counted and that the Trace lists it. Comments on `Message.fallback` and `search_count` are updated. ADR-0015 already records both decisions, so it is unchanged.

## Test seams

These tests use the [shared test seams](../../../specs/README.md#shared-test-seams); spec 13 adds none. No human was available to confirm seams, so these are the pre-agreed ones. The API seam is `backend/tests/integration/test_agentic_retrieval.py`: a scripted Pydantic AI `FunctionModel` against real Postgres and Redis, driven through the Draft and Playground HTTP API, with results read from the SSE stream and the Trace.

- `test_a_search_beyond_the_search_limit_is_refused_and_the_reply_still_answers` sets a Search limit of 2 and has the model make 3 calls. Only 2 `search` events stream. The model's third tool result is exactly the refusal text. The cited answer still streams. `search_count` is 2. The Trace lists all three calls, and the third has `limit_refused` true and no Chunks. (Red before the change: 3 search events.)
- `test_searched_and_found_nothing_gives_the_fallback_text_and_no_answer_tokens` uses Minimum Score 0.3 and an unrelated question. The events are exactly `search`, `token` (the Fallback Text), `done`, so the model's answer is never streamed. `fallback` is true. The Search's Chunks are all `below_min_score`. The Trace names the model, with 100 input tokens and a Cost above 0. (Red before: the model's answer streamed.)
- `test_a_greeting_needs_no_search` (from 13-02) covers a reply with no Search: it answers normally, `fallback` is false and it has no Searches.
- `test_a_chunk_two_searches_find_keeps_its_first_label_and_citations_span_searches` uses Top-k 1 and searches for leave, then expenses, then leave again. The third tool result names `[C1] leave.txt (given above)` without its text. The citations C2 and C1 resolve to Chunks from different Searches. `done.chunks` lists each Chunk once, in label order. The Trace shows the Chunk under both Searches with rank 1. (This passed on the base, which already had 13-01 and 13-02. The test pins it down at the API seam.)
- `test_a_provider_error_after_a_search_ends_with_a_typed_error_event` (from 13-02) covers a provider error after a Search: the events are `search`, then `error` with code `provider_error`, and no answer is saved.
- `test_remembered_turns_replay_only_the_visitors_and_the_agents_text` asks two questions in one Conversation. The second reply's first model call holds only system parts, then the earlier question and answer as plain text, then the new Visitor block. No tool call, tool return or Chunk is replayed. (This also passed on the base.)

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | A call beyond the Search limit is refused with the message; the reply still answers; the Trace shows limit-hit | `_knowledge_search`, `SEARCH_LIMIT_REACHED`; `test_a_search_beyond_the_search_limit_is_refused_and_the_reply_still_answers` |
| 2 | Searched with nothing at the Minimum Score: the Fallback Text replaces the model's answer, no answer tokens first, `fallback` true | `_found_nothing` in `_turn`; `test_searched_and_found_nothing_gives_the_fallback_text_and_no_answer_tokens` |
| 3 | No Search (a greeting): answers normally, not a fallback | `_found_nothing` needs at least one Search; `test_a_greeting_needs_no_search` |
| 4 | A Chunk found by two Searches keeps its first label and isn't re-sent; Citations resolve across Searches | `GivenChunks` (13-01), `search_results` (13-02); `test_a_chunk_two_searches_find_keeps_its_first_label_and_citations_span_searches` |
| 5 | A provider error after a Search ends with a typed error event | `run_turn` → `provider_error`; `test_a_provider_error_after_a_search_ends_with_a_typed_error_event` |
| 6 | Remembered turns replay only Visitor and Agent text | `prompt.history` from `Turn(question, answer)`; `test_remembered_turns_replay_only_the_visitors_and_the_agents_text` |
| 7 | Tests at the highest seam; 100% line and branch coverage | API seam tests above; [backend-tests.log](backend-tests.log) shows 100.00% coverage |
| 8 | Glossary and ADRs current | "Search limit" entry refined; "Fallback Text" already describes the Agentic case; ADR-0015 already records both decisions, so no ADR change was needed |

Standing criteria: there is no new Studio UI, so no frontend file changed and the palette ratchet does not apply.

## Results

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `cd backend && TEST_DATABASE_URL=…/studio_test_t04 TEST_REDIS_URL=redis://localhost:6379/11 uv run pytest -n 3` | 2565 passed, 4 failed; coverage 100.00% (12224 statements, 1524 branches), gate reached. The 4 failures are all in `tests/integration/test_logging.py`: each subprocess (API server, worker, beat) did not log its start line within 20 s under the load of four concurrent ticket suites (load average about 25 on 4 CPUs). Rerun alone, all 8 tests in that file pass. | [backend-tests.log](backend-tests.log), [rerun](backend-tests-rerun-logging.log) |
| Backend lint and types | `make lint-backend` (ruff check, ruff format --check, mypy) | exit 0 (395 files) | [lint-backend.log](lint-backend.log) |
| API client drift | `make check-client` | "API client is up to date.", exit 0 | [check-client.log](check-client.log) |
| Markdown links | `make link-check` | all resolve, exit 0 | [link-check.log](link-check.log) |

## Notes

- **Frontend and e2e.** This ticket changes no frontend file, end-to-end spec or API schema (the client is unchanged). The Playwright stack was not run here. The later integrated e2e run should cover `playground.spec.ts`, which holds the Agentic test from 13-02 and exercises this ticket's runtime path.
- **Decisions.**
  - A call refused by the Search limit streams no `search` event, so the Playground shows no "Searching" line for a search that never ran.
  - `search_count` (Messages, `done`, Trace) counts only the Searches that ran, so "searches per reply" (13-08) measures real retrieval work. The Trace's `searches` still lists the refused call.
