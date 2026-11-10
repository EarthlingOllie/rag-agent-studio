# Evidence: ticket 13-02, Agentic tracer: one Knowledge Search, end to end

Branch `t/13-02`, from `037bf379` (the integration branch with all of spec 12, plus merged `t/13-01`). The claim commit `8a1db4fc` set Status `in-progress`; the change is commit `ddb2a950`. Every check below ran at `ddb2a950`; only this folder and the ticket file were written afterwards.

**Status: done.** Every criterion is met and evidenced below.

## What was built

- **AgentConfig** (`backend/app/agents/config.py`): Retrieval gains `mode` (`RetrievalMode`: `automatic` | `agentic`, default **Automatic** until 13-09) and `search_limit` (1–5, default 3). The JSON Schema and the generated client (`frontend/packages/api-client`) are regenerated.
- **Runtime** (`backend/app/runtime/{runtime,prompt}.py`): `run_turn` keeps its signature. In Agentic mode there is no upfront search; the Pydantic AI agent gets exactly one tool, `knowledge_search(query)`, which calls the unchanged `retrieve` with the Agent's Retrieval settings and returns a spotlighted `<<<RETRIEVED_CHUNKS>>>` block (`search_results`): labels continue across the reply through 13-01's `GivenChunks`, a Chunk given before is named by its label alone, and nothing found says so. The question is the Visitor input block alone; the preamble is the Agentic preamble plus the search rules (`AGENTIC_RULES`). A `SearchEvent(query, order)` is streamed as each Search starts (the model is streamed in its own task and Searches are interleaved through a queue), and `DoneEvent.searches` lists each `Searched` (order, query, latency, candidates ranked by label number, excluded, `limit_refused`). Token use is the run's `RunUsage`, summed over every model call.
- **Persistence** (`backend/app/conversations/models.py`, migration `0040_searches`): a `searches` table (Message, order, query, latency, limit-refused); `message_retrievals.search_id` (null in Automatic mode); `messages.search_count`. Cost is computed from the summed tokens with the existing cost function.
- **API** (`backend/app/playground/{api,service}.py`): the Playground SSE stream sends `search` (`{query, order}`) events; `done` carries `search_count`. The Trace (Playground and Conversations viewer) returns `search_count` and `searches` in order, each with its Message retrievals nested; `chunks` keeps the Automatic search's retrievals. `answer()` streams SearchEvents only when asked (`searches=True`, the Playground); the widget's `search` event is 13-06.
- **Fake chat model** (`backend/app/gateway/fakes.py`): in Agentic mode it first makes one Knowledge Search with the Visitor's question, then answers citing `[C1]` as before.
- **Studio** (`frontend/apps/studio/src/projects/{agents.ts,AgentPage.tsx,Trace.tsx}`): the Playground shows a "Searching: *query*" line per Search, in reply order, above the answer; the Trace drawer lists the Searches (heading, latency, a Chunk table per Search) instead of the single "Retrieved Chunks" table. Design-system tokens and the shared `Icon` only.

## Test seams

The [shared test seams](../../../specs/README.md#shared-test-seams) (spec 13 adds none); no human was available to confirm seams, so these are the pre-agreed ones.

- **API seam** (`backend/tests/integration/test_agentic_retrieval.py`, scripted Pydantic AI `FunctionModel`, real Postgres and Redis):
  - `test_the_model_searches_the_search_streams_and_the_answer_cites_what_it_found`: Retrieval Mode set through the Draft API; the stream's first event is `search` with the model's query, then the answer and a `C1` citation; the Trace has `search_count` 1 and the Search with its cited Chunk nested.
  - `test_token_use_and_cost_are_summed_over_every_model_call`: two model calls give 100 input tokens (50 each) and 9 output tokens (5 for the tool-call arguments, 4 for the answer); Cost is `0.0000544` from GPT-4.1 mini's prices.
  - `test_a_greeting_needs_no_search`: no Search, no fallback, `searches == []`.
  - `test_model_written_queries_stay_inside_the_agents_tags_and_project`: the model asks for another Tag's product, another Project's text and another Organisation's text word for word; only the Agent's Tag material is given, the product is excluded `outside_tags`, and nothing from the other Project or Organisation is found.
  - `test_the_default_fake_chat_model_searches_once_with_the_visitors_question` and `..._answers_without_searching_in_automatic_mode`.
  - `test_a_provider_error_after_a_search_ends_with_a_typed_error_event`.
  - `test_a_visitor_of_an_agentic_live_version_gets_an_answer_and_its_search_is_traced` (widget answer; the Studio Conversations Trace lists the Search).
- **AgentConfig validation** (`test_agent_config.py`): defaults, full round trip with `mode`/`search_limit`, and `retrieval.mode` / `search_limit` 0 and 6 refused with where and why.
- **Prompt-assembly contract test** (`backend/tests/unit/test_prompt_assembly.py`): `test_agentic_mode_gives_the_model_knowledge_search_and_its_rules` asserts the whole Agentic transcript (preamble with rules, Visitor block, three Searches' tool results: labels continuing, a repeated Chunk named by label, delimiter escaping, nothing found), exactly one tool with only `query`, and no upfront search; `test_searches_made_at_once_are_numbered_in_the_order_they_start` covers parallel tool calls.
- **Frontend network seam (MSW)** (`AgentPage.test.tsx`): Searching lines in reply order; none without a Search; the Trace drawer's Searches with nested Chunk tables and a Chunk found again under its first label.
- **End-to-end** (`frontend/e2e/tests/playground.spec.ts`, new test): sets an Agent to Agentic through the Draft API, asks in the Playground, sees "Searching: …", a cited answer with its C1 chip, and "Search 1: …" with its cited Chunk in the Trace; axe clean.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | AgentConfig Retrieval gains `mode` and `search_limit` (1–5, default 3); Automatic by default; JSON Schema and client updated, drift check passes | `config.py`; `test_agent_config.py` (defaults, round trip, bounds); [check-client.log](check-client.log) "API client is up to date." |
| 2 | Agentic mode registers exactly one tool, Knowledge Search (`query`), calling the unchanged `retrieve` with the Agent's settings, returning spotlighted labelled blocks; no upfront search | `runtime._knowledge_search`, `prompt.search_results`; `app/retrieval` unchanged; contract test asserts the tool, the blocks and `asked == [model queries]`. |
| 3 | Agentic preamble rules added and covered by the prompt-assembly contract test | `prompt.AGENTIC_PREAMBLE`, `AGENTIC_RULES`; `test_agentic_mode_gives_the_model_knowledge_search_and_its_rules`. |
| 4 | `SearchEvent` streamed as each Search starts and sent as SSE `search` with its query | `runtime.SearchEvent`, `_with_searches`; Playground `search` event; API tests (first event is `search`), contract test, e2e. |
| 5 | Search record persisted; retrievals reference their Search; Messages store `search_count` | Model `Search`, `MessageRetrieval.search_id`, `Message.search_count`, migration 0040 (round trip and autogenerate check in `test_migrations.py`); API tests read them back through the Trace. |
| 6 | Token use summed over every model call; Cost from the sums | `test_token_use_and_cost_are_summed_over_every_model_call` (100/9 tokens, `$0.0000544`). |
| 7 | Trace returns Searches in order with nested retrievals; Playground "Searching: …" line; Trace drawer lists Searches with Chunks | `trace_out` (`searches`, `search_count`); API tests; MSW tests; e2e. |
| 8 | Tag scoping and Project isolation hold for model-written queries | `test_model_written_queries_stay_inside_the_agents_tags_and_project`. |
| 9 | Default fake chat model searches once with the question; e2e sees a Search line, a cited answer and a Search in the Trace | `fakes._search_first`; `test_the_default_fake_chat_model_searches_once_with_the_visitors_question`; e2e [e2e-affected.log](e2e-affected.log) test 5. |
| 10 | Automatic mode is unchanged | Every existing test passes unchanged apart from the fixtures that spell out a whole AgentConfig or Trace gaining the new fields (`tests/agents.py`, `full_draft` in `test_agent_config.py`, `test/agents.ts`): Playground, prompt-assembly, citations/Trace, canary, embed, tag-scoping suites ([backend-tests.log](backend-tests.log)); `..._answers_without_searching_in_automatic_mode`; Automatic e2e specs pass ([e2e-affected.log](e2e-affected.log)). |
| 11 | New Studio UI uses the design system; palette ratchet passes | Tokens (`text-muted`, `text-ink-2`, `border-line`…), `Icon`, `surface` only; [frontend-checks.log](frontend-checks.log): "0 palette-class uses". |
| 12 | Tests at the highest seam; 100% line and branch coverage | Seams above. Backend **100.00%** (12164 statements, 1494 branches); frontend 100% statements/branches/functions/lines. |
| 13 | Glossary / ADRs current | No new domain term: `GLOSSARY.md` already defines Retrieval Mode, Search, Search limit, Knowledge Search, Chunk label and Trace as built here (added with spec 13). ADR-0015 records the decision; nothing changed. |

## Results

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `TEST_WORKERS=auto make test-backend` (4 workers, own test database `studio_test_1302*` on the shared compose Postgres) | **2560 passed**, 0 failed in 23 min 59 s; coverage 100.00%; exit 0 | [backend-tests.log](backend-tests.log) |
| Backend lint and types | `make lint-backend` (ruff check, ruff format --check, mypy --strict) | exit 0 (395 files) | [lint-backend.log](lint-backend.log) |
| API client drift | `make check-client` | up to date, exit 0 | [check-client.log](check-client.log) |
| Frontend | `pnpm test && pnpm check-embed-size && pnpm palette-ratchet && pnpm lint && pnpm typecheck` | 1087 tests passed, 100% coverage, 0 palette classes, exit 0 | [frontend-checks.log](frontend-checks.log) |
| Affected e2e | Playwright `studio` project, 1 worker: playground, playground-errors, playground-instructions, tag-scoping, conversations, reranker | **7 passed** (including the new Agentic test) | [e2e-affected.log](e2e-affected.log) |
| Draft/embed e2e | agent-config, agent-drafts, agent-revert, embed, token-budget | 3 passed, 2 failed (pre-existing, see below) | [e2e-config-embed.log](e2e-config-embed.log) |

The e2e stack is the committed `docker-compose.yml` run as its own project (`-p rag1302e2e`) beside the shared services, with the sandbox-only override [compose.e2e.yml](compose.e2e.yml) (images built by [build.sh](build.sh) from this worktree, host ports moved to 5273/5275/5276/8125); its API image's `app/` and `migrations/` were diffed against `ddb2a950` and are identical.

## Notes and gaps

- `agent-config.spec.ts` (Greeting not found after a reload: settings groups fold) and `embed.spec.ts` (axe `label-content-name-mismatch` on "Copy Embed Snippet" showing "Copied") fail on this base with the same assertions as in the spec-12 stack run before its fixes (`12-08-evidence/e2e-stack-full.log`). Both are fixed by `707140bb` ("Spec 12: the compose-stack e2e suite passes"), which is on the integration branch but not an ancestor of this ticket's base `037bf379`; neither touches 13-02's code.
- A first e2e attempt ran beside the backend suite and the browser pages crashed for lack of memory; it was rerun alone with one worker (above).
- Out of scope here, by the ticket split: the Search limit refusal and Agentic fallback (13-04), tool-support checks (13-03), the widget `search` event and Token Budget (13-06), canary checks on queries (13-07), query purging and metrics (13-08), the editor control (13-05) and the Agentic default (13-09). `limit_refused` is stored (always false until 13-04).
