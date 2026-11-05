# Evidence: ticket 04-03, Hybrid retrieval and fallback

Branch `ticket/04-03-hybrid-retrieval-fallback`, from `origin/candidate` at `59d696a` (04-01, the only blocker, merged), later updated from `origin/candidate` at `570cba4`. The claim commit, the first on the branch, set Status `in-progress`.

**Status: done.** Every criterion is met and evidenced below. The gaps at the end are scope this ticket leaves to later tickets on purpose, plus what this sandbox can't run.

## What was built

Retrieval now combines semantic and keyword search, so exact terms such as product codes are found. A minimum score makes the Agent reply with its fallback text, without asking the model, when nothing relevant is found. Every Chunk retrieval found but left out comes back with its reason.

- **AgentConfig** (`backend/app/agents/config.py`) gains three settings, each with a default so stored Drafts stay valid:
  - `behaviour.fallback_text`: 1 to 2000 characters, default "Sorry, I don't know the answer to that."
  - `retrieval.hybrid_weight`: 0 to 1, default 0.5. This is semantic search's share of the fused score. 1 means semantic search alone and 0 means keyword search alone.
  - `retrieval.min_score`: 0 to 1, default 0, so nothing is filtered until an Editor sets it.
- **Retrieval module** (`backend/app/retrieval/service.py`). The `retrieve(session, project, query, settings, embedders)` interface is unchanged. It now works in four steps:
  1. **Semantic search:** pgvector cosine search, as in 04-01. The semantic score is the cosine similarity.
  2. **Keyword search:** Postgres full-text search on the existing `chunks.search_vector` GIN index (`simple` configuration). It finds Chunks containing any of the query's terms. The keyword score is the share of the query's distinct terms a Chunk contains. Postgres extracts the terms with the same configuration the index uses, at most 64 of them.
     - Both searches are limited to the Project, its active Embedding Model and the current edition of Ready Documents. Each returns at most 50 Chunks.
     - A search whose weight is 0 is not run.
  3. **Weighted reciprocal rank fusion** (k = 60): `score = Σ weight / (60 + rank)`. It is scaled by 61, so 1 means first in every search. Candidates are ranked by this score.
  4. **Minimum score, then top-k.** A Chunk's **relevance** is its better semantic or keyword score. Chunks whose relevance is below `min_score` are excluded with reason `below_min_score`. The best `top_k` of the rest become candidates, and the others are excluded with reason `outside_top_k`.
  - `Candidate` gains `relevance`, `semantic_score` and `keyword_score`. `Excluded` carries the Chunk, its Document, its fused score, its relevance and its reason.
- **Agent runtime** (`backend/app/runtime/runtime.py`). When retrieval returns no candidates, `run_turn` yields the fallback text as a single token and then a `DoneEvent(fallback=True)` with zero tokens. The model is never asked. `DoneEvent` now carries `excluded` for every turn.
- **Playground SSE `done` event** gains:
  - `fallback`;
  - `relevance` on each entry in `chunks`;
  - `excluded`: `[{chunk_id, score, relevance, reason}]`.

  The fallback reply is saved as the assistant Message, with 0 tokens and a cost of 0.
- **Studio:** saving the Draft form (system prompt and top-k) now keeps the Draft's other settings instead of resetting them to defaults. The full editor for the new fields is ticket 04-07.
- **Generated API client** regenerated (`make gen-client`), because the AgentConfig schema changed.

### Design decision: why the minimum score applies to relevance, not the fused score

An RRF score depends only on ranks. The nearest Chunk always ranks first in semantic search, however unrelated it is, so a threshold on the fused score can never tell that nothing relevant was found. Relevance is an absolute measure, so the threshold is compared against it, while the fused score only orders the Chunks.

Keyword relevance is the share of the query's terms a Chunk contains, rather than `ts_rank`. Its scale (0 to 1, where 1 means every term) is comparable to cosine similarity and easy for an Editor to reason about. This refines how [ADR-0001](../../../adr/0001-pgvector-hybrid-search.md) is applied; it does not change the decision (pgvector plus `tsvector`, fused with RRF), so no ADR was changed.

## Test seams

These follow the [shared test seams](../../../specs/README.md#shared-test-seams).

- **Retrieval through its interface:** `backend/tests/integration/test_retrieval.py` runs against real Postgres with pgvector and the deterministic hash embedder.
  - The fixture Knowledge Base is `backend/tests/knowledge_base.py`: six one-Chunk files, uploaded through the API and ingested eagerly.
  - Its design makes relevance known. Semantic search finds a Chunk only by its exact text. `PRODUCT` ("Model SKU-4471 …") can only be found by keyword. `RULES` and `RULES_REPEATED` are ranked in opposite orders by the two searches.
- **API seam:** `test_playground.py` and `test_agents.py` run in process against real Postgres and Redis. The chat model is the gateway's fake adapter returning a Pydantic AI `FunctionModel`. A `never_called` stream function fails the test if the model is asked.
- **Prompt-assembly contract test:** `tests/unit/test_prompt_assembly.py` is updated for the new `Candidate` fields. Its empty-config case now retrieves one Chunk, because no Chunks now means the fallback.
- **Network seam:** `AgentPage.test.tsx` uses MSW.
- **End-to-end seam:** `make e2e` runs the existing suite unchanged, including `playground.spec.ts`. That spec still streams a model answer, because the default minimum score is 0.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Full-text and vector results are fused with weighted RRF using the hybrid-weight setting | **Code:** `app/retrieval/service.py`. `_semantic` and `_keyword` feed `fuse()`, which computes `weight · 61/(60 + rank)`. The weights are `hybrid_weight` and `1 − hybrid_weight`, and a search weighted 0 is skipped. `Retrieval.hybrid_weight` is in `app/agents/config.py`.<br>**Tests** (`test_retrieval.py`):<br>• `test_the_relevant_chunk_ranks_first_with_its_scores`: first in both searches gives a fused score of exactly 1, and the per-search scores are reported.<br>• `test_the_hybrid_weighting_decides_between_the_searches`: at weight 0.8 `RULES` comes first, and at 0.2 `RULES_REPEATED` does. The fused score equals `0.2·61/61 + 0.8·61/62`, a hand-computed value.<br>• `test_keyword_search_alone_finds_only_chunks_sharing_words` (weight 0).<br>• `test_a_chunk_only_keyword_search_finds_is_retrieved` (weight 1 against the default). |
| 2 | When no Chunk passes the minimum score, the Agent replies with its fallback text | **Code:** `run_turn` in `app/runtime/runtime.py`; `Behaviour.fallback_text` and `Retrieval.min_score` in `config.py`.<br>**Tests** (`test_playground.py`, through the API):<br>• `test_with_nothing_relevant_the_agent_replies_with_its_fallback_text`: with `min_score` 0.3 and a custom fallback, the stream is exactly one token with the fallback text, then `done` with `fallback: true`, `chunks: []`, 0/0 tokens. The model is never called. The saved Message holds the fallback text with cost 0.<br>• `test_a_project_without_documents_replies_with_the_fallback_text`: the default fallback text.<br>• `test_a_relevant_chunk_above_the_minimum_score_reaches_the_model`: the counter-case. The keyword-only hit clears 0.3 and is the only Chunk in the prompt.<br>• Validation in `test_agents.py`: `test_an_invalid_draft_is_refused` covers an empty or over-long fallback text, and `hybrid_weight` or `min_score` outside 0 to 1. `test_the_draft_is_saved_and_read_back_exactly` and `test_a_partial_draft_takes_defaults_for_the_rest` cover the round-trip and the defaults. |
| 3 | Excluded candidates are returned with their reasons | **Code:** `RetrievalResult.excluded: list[Excluded]` with `reason ∈ {below_min_score, outside_top_k}`. It is passed through `DoneEvent.excluded` and the SSE `done.excluded`.<br>**Tests:**<br>• `test_chunks_below_the_minimum_score_are_excluded_with_their_reason`: every Chunk is excluded with its relevance. For `PARKING`, the relevance is 1/5 = "the", 1 of 5 query terms.<br>• `test_chunks_beyond_top_k_are_excluded_with_their_reason`<br>• `test_a_chunk_only_keyword_search_finds_is_retrieved`: the semantic-only miss is excluded as `below_min_score`.<br>• Through the API: `done.excluded` in both fallback tests above. |
| 4 | A fixture Knowledge Base covers hits only keyword search finds, the effect of weighting, the threshold, and isolation | The fixture is `backend/tests/knowledge_base.py`. Each case and its test:<br>• **Keyword-only hit:** `test_a_chunk_only_keyword_search_finds_is_retrieved`. `PRODUCT_QUESTION` finds `PRODUCT` with keyword score 3/6; semantic search alone finds nothing above 0.3.<br>• **Weighting:** `test_the_hybrid_weighting_decides_between_the_searches`.<br>• **Threshold:** `test_chunks_below_the_minimum_score_are_excluded_with_their_reason`, where 0.3 excludes everything and 0.1 lets only the weak keyword match through. Also the Playground fallback tests.<br>• **Project and Organisation isolation:** `test_only_the_projects_own_chunks_are_searched`, for both searches. A sibling Project holds a `PRODUCT` look-alike and another Organisation holds the whole fixture.<br>• **Embedding Model isolation:** `test_only_chunks_of_the_active_embedding_model_are_searched`, for both searches.<br>• `test_a_question_without_words_finds_nothing_by_keyword`. |
| 5 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | See the seams above and the results below:<br>• Backend `pytest` gate: `fail_under = 100`, branch coverage on. `app/retrieval/service.py` 110 statements and 22 branches, `app/runtime/runtime.py` 37 and 4, both 100%.<br>• Frontend Vitest gate: 100%. |
| 6 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md` (Agents and versioning) gains **Hybrid search**, **Hybrid weighting**, **Relevance**, **Minimum Score**, **Fallback Text** and **Excluded Chunk**. No ADR changed; see the design decision above. |

## Results

All runs are local, one suite at a time (GitHub Actions is down; the user authorised merging on local results). They were re-run on merge commit `8693632`, after merging `origin/candidate` at `c1e455f` (03-06 Tags). The merge was clean. Candidate then moved to `570cba4`, which adds only `docs/screenshots/`; after merging it (`48b16f0`), `make lint` was re-run and passed. Nothing else it touches is checked by a suite.

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `make test-backend` against the `rag0403` Postgres/pgvector, Redis and RustFS containers | **973 passed**, 5 deselected (live); coverage **100.00%** lines and branches (4997 statements, 466 branches) | [backend-tests.log](backend-tests.log) |
| Frontend tests + coverage gate | `make test-frontend` | **31 files, 322 tests passed**; 100% coverage | [frontend-tests.log](frontend-tests.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc) | exit 0 (at `8693632` and `48b16f0`) | [lint.log](lint.log) |
| API client drift | `make check-client` | "API client is up to date." | [client-drift.log](client-drift.log) |
| Security | gitleaks (`origin/candidate..HEAD`), `make audit` (pip-audit, pnpm audit) | no leaks, no known vulnerabilities | [security.log](security.log) |
| Images | `build.sh` (sandbox `make images`) | both built | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` (project `rag0403`) | **44 passed**, including `playground.spec.ts` and 03-06's `tags.spec.ts` | [e2e.log](e2e.log) |
| Infra | terraform fmt/validate/test | not run: this ticket changes no infra | n/a |

## Gaps and best guesses

- **Out of this ticket's scope, left to the tickets named:**
  - Tag scoping (04-04).
  - The reranker (04-05). It would slot in between fusion and the minimum score; relevance would then be the reranker's score.
  - Saving Message retrieval rows with the excluded reason, and the Trace drawer (04-06). For now `excluded` is returned by `retrieve`, carried on `DoneEvent` and streamed in `done`, but not saved.
  - Studio fields for the fallback text, hybrid weighting and minimum score (04-07). They can be set through the Draft API today.
- **Best guesses, recorded instead of asking:**
  - The minimum score applies to relevance (the better per-search score), not the fused RRF score. The reason is in the design decision above.
  - Default `min_score` is 0, so behaviour is unchanged until an Editor sets it. A non-zero default would make the fallback fire for almost every question under the deterministic test embedder, and its right value depends on the Embedding Model.
  - A Project with no Chunks now replies with the fallback text instead of asking the model with an empty Chunks block, which is how 04-01 behaved.
  - The fallback reply is saved with the Default Model's provider and name, 0 tokens and cost 0, so the Message shape stays uniform. The model is not called.
  - The tests could not confirm the test seams with a human. They use the seams the spec's Testing Decisions name: retrieval through its interface, and the Playground API.
- **Sandbox limits** (as in 04-01): the images are built with `WITH_PDF=false BUNDLE_MODELS=false` and the e2e stack runs `EMBEDDER=fake`, because Hugging Face is blocked here. The live suite (real embedding model) and the Trivy image scan were not run. This ticket adds no dependencies.
