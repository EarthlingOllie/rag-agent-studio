# Evidence: ticket 04-01, Agent and Playground tracer

Branch `ticket/04-01-agent-playground-tracer`, from `origin/candidate` at `0a6a9e7` (03-02 and 02-03, the two blockers, merged). The claim commit, the first on the branch, set Status `in-progress`.

**Status: done.** Every criterion is met and evidenced below. The gaps at the end are scope this ticket leaves to later tickets on purpose, plus what this sandbox can't run.

## What was built

An Editor creates an Agent in a Project and writes its system prompt. They then chat with its Draft in the Playground, and the answer streams back token by token. The answer comes from the Organisation's Default Model, through the model gateway, and is grounded in Chunks retrieved from the Project's Knowledge Base.

- **Backend modules:**
  - `app/agents/`: the `AgentConfig` model, Agents and Drafts, and the Agent API.
  - `app/retrieval/`: the retrieval module, `retrieve(...)`.
  - `app/runtime/`: the Agent runtime, `run_turn(...)`, and prompt assembly.
  - `app/conversations/`: the Conversation and Message tables.
  - `app/playground/`: the Playground API and its Server-Sent Events stream.
  - Migration `0012_agents_conversations` adds the tables `agents`, `agent_drafts`, `conversations` and `messages`.
- **Studio:**
  - The Agents tab on the Project page, which replaces the placeholder. It lists the Project's Agents and has a create form.
  - The Agent page, `/organisations/$organisationId/projects/$projectId/agents/$agentId`. It shows the Draft form (system prompt and top-k) beside the Playground panel, which renders the stream as it arrives.
- **Generated API client** regenerated (`make gen-client`).

## Test seams

These follow the [shared test seams](../../../specs/README.md#shared-test-seams).

- **API seam.** Tests use `tests/integration/test_agents.py`, `test_playground.py` and the extended `test_tenant_isolation.py` and `test_openapi.py`. They run the app in process against real Postgres with pgvector and real Redis. Ingestion runs eagerly through the fake converter and the deterministic embedder. The chat model is a Pydantic AI `FunctionModel`, plugged in through the gateway's fake adapters (`tests/agents.py::answer_with`), the only seam the gateway allows.
- **Retrieval through its interface.** `tests/integration/test_retrieval.py` calls `retrieve()` against real Postgres and pgvector, on a Knowledge Base uploaded through the API.
- **Prompt-assembly contract test.** `tests/unit/test_prompt_assembly.py` uses an echoing `FunctionModel`. It is the one test that asserts on prompt strings, as the spec intends.
- **Network seam.** `AgentsTab.test.tsx` and `AgentPage.test.tsx` use MSW. The streaming handler (`test/agents.ts::streamedAnswer`) returns a `ReadableStream` that splits events across reads.
- **End-to-end seam.** `frontend/e2e/tests/playground.spec.ts` runs against the containerised compose stack, with axe.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | The AgentConfig Pydantic model starts with system prompt and top-k, is stored on the Agent's Draft, and the Agent gets a public ID | **Code:**<br>• `app/agents/config.py`: `AgentConfig{behaviour: {system_prompt}, retrieval: {top_k 1–20, default 5}}`. Unknown fields are refused (`extra="forbid"`). Later tickets add fields with defaults. In responses every field is required (`json_schema_serialization_defaults_required`), so the generated client types a saved config as complete.<br>• `app/agents/models.py`: `Agent` has `public_id` = `agt_` + `secrets.token_urlsafe(18)` (144 random bits, unique index), `project_id`, `organisation_id` and `archived_at`. `AgentDraft` is one row per Agent, holding the config as `jsonb`, validated with `AgentConfig.model_validate` on every read.<br>• The API is `listAgents`, `createAgent` (records `agent.created`), `getAgent` and `saveAgentDraft` (PUT, body `AgentConfig`).<br>**Tests** (`test_agents.py`):<br>• `test_an_editor_creates_an_agent_with_a_public_id_and_a_default_draft`: public ID format and uniqueness, the default Draft, the Audit Event.<br>• `test_the_draft_is_saved_and_read_back_exactly`: markdown round-trips.<br>• `test_an_invalid_draft_is_refused` (top-k 0 and 21, an over-long prompt, unknown fields) and `test_a_partial_draft_takes_defaults_for_the_rest`.<br>• `test_a_project_lists_its_agents_and_counts_them`: `agent_count` on Projects is now real.<br>• Not-found and archived-Project tests. |
| 2 | The retrieval module runs vector search limited to the Project and its active Embedding Model | **Code** (`app/retrieval/service.py`): `retrieve(session, project, query, Retrieval settings, embedders) → RetrievalResult(candidates, excluded)`.<br>• It embeds the query with the embedder for `project.embedding_model_id`.<br>• It runs pgvector cosine distance on `embedding::vector(dim)`, so the per-model HNSW index applies.<br>• The search is limited to `Chunk.project_id`, `Chunk.embedding_model_id` = the Project's model, Ready Documents, and each Document's current edition. It orders by distance and stops at top-k.<br>• Score = 1 − cosine distance. Rank starts at 1.<br>• `excluded` is empty until the threshold, Tags and the reranker arrive (04-03 to 04-05).<br>• The embedder port gained `embed_query`: the e5 query prefix for the local model, and passage-equal hashing for the fake, so a query equal to a Chunk's text finds it with score 1.<br>**Tests** (`test_retrieval.py`, real Postgres and pgvector):<br>• `test_the_relevant_chunk_ranks_first_with_its_score`<br>• `test_top_k_limits_the_candidates`<br>• `test_only_the_projects_own_chunks_are_searched`: a sibling Project and another Organisation hold the same text.<br>• `test_only_chunks_of_the_active_embedding_model_are_searched`<br>• `test_a_project_whose_embedding_model_has_no_embedder_cant_be_searched` |
| 3 | The Agent runtime assembles the prompt in a fixed order with spotlighting blocks, registers no tools, and uses the Default Model through the gateway | **Code** (`app/runtime/`):<br>• `run_turn(turns, config, instructions, visitor_input, *, model, retrieve)` is an async stream of `TokenEvent`s, then a `DoneEvent` with the answer, token usage and retrieved Chunks. It knows nothing about HTTP.<br>• `prompt.py` assembles in a fixed order:<br>&nbsp;&nbsp;1. The platform preamble (the spotlighting rules).<br>&nbsp;&nbsp;2. The Project Instructions.<br>&nbsp;&nbsp;3. The Agent's system prompt.<br>&nbsp;&nbsp;4. The remembered turns.<br>&nbsp;&nbsp;5. One user message holding the `<<<RETRIEVED_CHUNKS>>>` block (Chunks labelled `[C1]`…) and the `<<<VISITOR_INPUT>>>` block.<br>• Delimiters inside data are escaped, so data can't close its block. Empty Instructions or an empty system prompt are left out, because providers refuse empty system text.<br>• `pydantic_ai.Agent(model)` is built with no tools and no output tools (ADR-0007).<br>• `app/playground/service.py` reads the Organisation's Default Model (`read_default`) and builds it with `ModelGateway.chat_model`. With no Default Model, the question is refused with 409 and nothing is saved.<br>**Tests:**<br>• The contract test (criterion 6) asserts the exact order, the escaping and `function_tools == output_tools == []`.<br>• `test_an_editor_asks_the_draft_and_the_answer_streams_back` asserts the gateway built `openai:gpt-4.1-mini`, the Default Model set through the API.<br>• `test_the_model_receives_the_draft_the_chunks_and_the_history_in_order` checks the same order through the API.<br>• `test_the_question_needs_a_default_model`<br>• `test_an_unanswered_question_is_not_remembered` |
| 4 | Conversations (with a Playground flag) and Messages (with tokens and latency) are saved | **Schema** (migration `0012`, `app/conversations/models.py`):<br>• `conversations`: `agent_id`, `is_playground`, `last_activity_at` and `organisation_id`.<br>• `messages`: `seq` (identity, for ordering), `role`, `content`, `config_source` (`draft`), `model_provider`, `model_name`, `input_tokens`, `output_tokens`, `first_token_ms`, `latency_ms`, `cost_usd` (from spec 02's `cost()` with the credential's overrides and the platform price table) and `organisation_id`.<br>• The question is saved before the stream starts. The answer is saved, with its usage, when the stream ends.<br>• `getPlaygroundConversation` reads both back.<br>**Tests:** `test_an_editor_asks_the_draft_and_the_answer_streams_back` reads the saved Conversation through the API: `is_playground` true, the user and assistant Messages, tokens matching the `done` event, `0 ≤ first_token_ms ≤ latency_ms`, the model, `config_source == "draft"` and a positive cost. The isolation guard `test_every_table_below_the_platform_level_carries_an_organisation_id` covers the four new tables. |
| 5 | The Playground SSE endpoint streams token and done events, and the Playground UI renders them | **API** (`app/playground/api.py`):<br>• `startPlaygroundConversation` (POST).<br>• `sendPlaygroundMessage` (POST `…/playground/conversations/{id}/messages`) answers `text/event-stream`: one `event: token` per model delta (`{"text"}`), then `event: done` with `{message_id, input_tokens, output_tokens, first_token_ms, latency_ms, chunks:[{chunk_id, score, rank}]}`. The headers are `Cache-Control: no-cache` and `X-Accel-Buffering: no`.<br>• Editor or Owner, through the one policy dependency.<br>**Studio:**<br>• `projects/agents.ts::askPlayground` reads the stream through the typed client (`parseAs: "stream"`) and parses events that are split across reads.<br>• `AgentPage.tsx` renders the user message, then appends tokens to the answer as they arrive. It shows "N input and M output tokens · X ms" on `done`, keeps one Conversation per page, and shows an error for a refusal or a cut-off stream.<br>**Tests:**<br>• API: the stream's exact events in order (`test_an_editor_asks_the_draft_and_the_answer_streams_back`).<br>• Network seam: `a question is answered in the Playground as the answer streams in` (a chunked MSW stream), `a refused question shows the API's reason`, `an answer cut off before it ends shows an error`, `a Playground that can't start says so` and `a blank question isn't sent`. |
| 6 | A prompt-assembly contract test uses an echoing `FunctionModel` | `backend/tests/unit/test_prompt_assembly.py::test_the_prompt_is_assembled_in_a_fixed_order_with_spotlighted_data`. The `FunctionModel` streams back every part it received. The test asserts:<br>• the exact sequence: preamble, Instructions, system prompt, two remembered turns, then the Chunks block (two Chunks, one trying to forge `<<<END_RETRIEVED_CHUNKS>>>`) and the Visitor input block (also trying to forge its end);<br>• that both forgeries are escaped;<br>• that no tools are registered;<br>• that `retrieve` was asked with the question and the Draft's top-k.<br>A second test checks that empty Instructions and an empty system prompt are left out. The API-level `test_the_model_receives_the_draft_the_chunks_and_the_history_in_order` uses an echoing `FunctionModel` through the whole Playground route. |
| 7 | End-to-end: create an Agent → ask a question → receive a streamed answer | `frontend/e2e/tests/playground.spec.ts`:<br>1. Set the Default Model through the API (fake verifier).<br>2. Create a Project and upload the seed handbook, then wait for Ready. The real worker and real Docling run on Markdown.<br>3. On the Agents tab, create "HR helper" and save a system prompt.<br>4. axe scan.<br>5. Ask a question. The streamed answer `Fake reply from anthropic:claude-haiku-4-5.` (the compose stack's fake gateway model) arrives with its usage line.<br>6. axe scan again.<br>7. Reload: the Draft persisted.<br>**Runs:** see [e2e.log](e2e.log) and the e2e results below. |
| 8 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | See the seams above, and the results below for the backend `pytest` gate (`fail_under = 100`, branch on) and the frontend Vitest gate (100% lines, branches, functions and statements). |
| 9 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md` gains **AgentConfig**, **Public ID**, **Top-k**, **Spotlighting** (under Agents and versioning) and **Playground Conversation**. No decision changed. ADR-0001 (`organisation_id` on every table, including `agent_drafts`), ADR-0007 (no tools) and ADR-0009 (Operational Settings and Theme outside AgentConfig) are followed as written. |

## Results

All runs are local (GitHub Actions is down; the user authorised merging on local results). Suites ran one at a time.

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `make test-backend` against the `rag0401` Postgres/pgvector, Redis and RustFS containers | **899 passed**, 5 deselected (live); coverage **100.00%** lines and branches (4671 statements, 426 branches) | [backend-tests.log](backend-tests.log) |
| Frontend tests + coverage gate | `make test-frontend` | **30 files, 308 tests passed**; 100% statements, branches, functions and lines | [frontend-tests.log](frontend-tests.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc) | exit 0 | [lint.log](lint.log) |
| API client drift | `make check-client` | "API client is up to date." | [client-drift.log](client-drift.log) |
| Security | gitleaks (this branch), pip-audit, pnpm audit | no leaks, no known vulnerabilities | [security.log](security.log) |
| Images | `build.sh` (sandbox `make images`) | both built | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` | **42 passed, 1 failed**; the new `playground.spec.ts` passed. The failure was the pre-existing `mfa.spec.ts` enrol test (01-11), a timing failure under machine load; it is untouched by this ticket and passed on re-run (2/2) | [e2e.log](e2e.log), [e2e-mfa-rerun.log](e2e-mfa-rerun.log) |

The last line of `backend-tests.log` is a telemetry span the console exporter flushes at exit. It is from the gateway's fake Anthropic transport (`msg_01`), not a real provider call.

## Gaps and best guesses

- **Out of this ticket's scope, left to the tickets named:**
  - Hybrid full-text fusion, the minimum score, and the fallback text (04-03).
  - Tag scoping (04-04).
  - The reranker (04-05).
  - Citations and the Trace drawer, and Message retrieval rows (04-06).
  - The full AgentConfig editor with autosave, the model override, temperature and remembered-turn limits (04-07). For now every earlier turn of the Conversation is remembered.
  - Provider errors as typed `error` events in the stream, and Playground reset (04-08).
  - Agent Archive and delete (04-09).
  - Project Instructions editing (05-01). The runtime already takes the Instructions text, and the Playground passes `""` until then.
  - The canary placeholder in the preamble (08-04).
  - Credential references from AgentConfig: there are no credential fields in the config yet (04-07).
  - The spec's "Playground Conversations excluded from metrics" placeholder assertion. There are no metrics queries yet; spec 07 adds them, and `is_playground` is the flag they filter on.
- **Best guess, recorded instead of asking.** A mid-stream provider failure currently ends the stream without a `done` event. The Studio shows "Something went wrong" and drops the half answer, and the question stays saved without an answer. The runtime skips such unanswered questions when building the remembered turns (`test_an_unanswered_question_is_not_remembered`). 04-08 turns provider failures into typed `error` events.
- **Sandbox limits:**
  - The images are built with `WITH_PDF=false BUNDLE_MODELS=false` and the e2e stack runs `EMBEDDER=fake`, as in 03-02, because Hugging Face is blocked here.
  - The Trivy image scan (`make image-scan`) was not run for this ticket: the sandbox images are built without PDF and models, so a scan would not represent the shipped image. The images change only by this ticket's Python and TypeScript sources, no new dependencies.
  - No live-suite test was added for a real chat model. That needs a real provider key, which this sandbox must not use.
  - The machine ran eight tickets' suites at once (load average 35–290 on 4 CPUs). Pre-existing tests timed out at random under that load in some runs; see the results above for what was done about it.

## Files

| File | What it is |
|---|---|
| `build.sh` | Sandbox-only `make images`: the committed Dockerfiles plus the egress proxy CA, PDF and models off |
| `compose.sandbox.yml`, `e2e.env` | Port and image override, and environment, for `make e2e` beside other tickets' stacks |
| `images.log` | The two image builds |
| `backend-tests.log`, `frontend-tests.log`, `lint.log`, `client-drift.log`, `security.log`, `e2e.log`, `e2e-mfa-rerun.log` | The runs summarised under Results |
