# Evidence: ticket 13-09, Agentic by default, with the demo and seed

Branch `t/13-09`, from `a6ae0d1f`: the integration branch with all of spec 12 and every other spec 13 ticket (13-01 to 13-08) merged. This is the first branch where 13-07 meets 13-03, 13-05, 13-06 and 13-08. The change is commits `1ca80295` to `acbe2d72`; every check below ran on `acbe2d72` unless its row says otherwise. Only this folder and the ticket file were written afterwards.

**Status: done.** Every criterion is met and evidenced below. The real-provider live test is written and skips without a key (no key exists here), and the Playwright run is deferred to the integrated branch; both gaps are recorded at the end.

## What was built

- **Agentic by default** (`backend/app/agents/config.py`): `Retrieval.mode` defaults to `RetrievalMode.AGENTIC`. The JSON Schema and the generated client (`frontend/packages/api-client`) are regenerated (`@default agentic`). As the spec says, only the seed creates Agents, so there is no data migration; an Agent's saved Draft and Versions keep the mode they were saved with.
- **Demo models in Agentic mode** (`backend/app/gateway/demo.py`): offered Knowledge Search, the **Demo model** (`demo-chat`) makes one Knowledge Search with the Visitor's question (the Visitor input block's text, or everything asked when there is none), then answers as before, from the first Chunk that Search returned, quoted and cited `[C1]`. Searches that found nothing give its "nothing on that" answer, and the runtime's Agentic fallback then sends the Fallback Text. The streamed and the non-streamed paths both search. The **Naive demo model** (`demo-naive`) searches as the suite's Naive model does (`naive_search`): first with the Visitor's question, then answers from the first Chunk it got. Like the Naive model, it searches a second time only when a result tells it to search for its secret token, which is the attack the 13-07 eval case covers. Both work in the fake and live adapter sets, so the demo needs no key in `docker compose` or AWS.
- **Seed** (`backend/app/seed/content.py`, `runner.py`): `SeedAgent.mode` is required, and the seed writes it into every seeded Agent's Draft (and so into its Versions):
  - **Product FAQ: Agentic.** It is the shop pages' Agent, so Visitors also see the widget's searching status.
  - **HR helper: Automatic.** It is the Agent of the analytics story, whose v1 to v3 history is unchanged.
  - **Low-budget helper: Automatic.**
  - **Guardrail demo: Automatic**, so the Attack panel stays deterministic.

  All four Agents are over the one Northwind Handbook Project. Seeding again puts a changed mode back, as it does for any other seeded setting.
- **Five-minute demo** (`README.md`): step 3 is now "The Agent editor and two Playground Traces". It compares the HR helper's Automatic Trace (one search up front, one Retrieved Chunks table) with the Product FAQ's Agentic one ("Searching: …" in the Playground, then Search 1 with the query the model wrote and its Chunks). It spells out the trade-off. Step 5 notes the widget's "Searching the knowledge base…" status.
- **Live suite** (`backend/tests/live/test_agentic_reply_live.py`): see the live-suite row below. `tests/live/models.py`'s `_skip_or_fail` is now the public `skip_or_fail`, so this test shares the `LIVE_REQUIRE_MODELS=1` rule. `make test-live`'s help and `docs/development.md` describe the new test.
- **Docs**: `GLOSSARY.md` updates **Demo Organisation** (one Agentic and one Automatic Agent, the mode always set explicitly, the Guardrail demo Agent Automatic), **Five-minute demo** (the two Traces), **Demo model** (searches, then answers from the first Chunk its Search returned) and **Naive demo model** (searches as the Naive model). There is no new domain term: **Retrieval Mode** already said "New Agents start Agentic". ADR-0015 is unchanged, since no decision changed.

## Test seams

These tests use the [shared test seams](../../../specs/README.md#shared-test-seams); spec 13 adds none. No human was available to confirm seams, so these are the pre-agreed ones.

- **API seam, the seed** (`backend/tests/integration/test_seed.py`, real Postgres and Redis, Docling on the seed Documents, the seed driven through the API):
  - `test_one_agentic_and_one_automatic_agent_show_the_trade_off_without_a_real_key`. The Draft and the Live Version's config have Product FAQ `agentic`, and HR helper, Low-budget helper and Guardrail demo `automatic`, all in one Project. Asked "Can I return a jar of honey?" in the Playground, the Product FAQ's first event is `search` with exactly that query. The answer is the Demo model's quote of the first Chunk of Search 1, which is `rank` 1 and cited. Its Trace has `search_count` 1 and no up-front `chunks`. The HR helper streams no `search`, answers from the staff handbook, and its Trace has no Searches and a cited up-front Chunk. It was red before the change: every Agent was `agentic`.
  - `test_seeding_again_puts_back_what_was_changed`: it now also flips the HR helper to Agentic, and a re-seed puts back `automatic`.
  - `test_the_demo_model_is_labelled_and_answers_without_any_api_key` (unchanged): the Product FAQ, now Agentic, still answers with the demo label and cites C1. It failed after the default flip and before the demo-model change.
- **Demo provider** (`backend/tests/unit/test_model_gateway.py`, through the gateway with both adapter sets):
  - `test_given_knowledge_search_the_demo_models_search_once_with_the_question_then_answer`, for `demo-chat` and `demo-naive`, fake and live adapters. Each model makes exactly one Search with the question, then answers from C1 of the Search's result under its own label. It was red before: no Search was made.
  - `test_the_demo_model_searches_before_answering_when_not_streamed`: the non-streamed path searches with the whole prompt when there is no Visitor block. A Search that found nothing gives "the Knowledge Base has nothing on that."
- **AgentConfig default** (`test_agent_config.py::test_a_new_agents_draft_has_every_group_at_its_defaults`): `FULL_DEFAULT_DRAFT` now has `"mode": "agentic"`. It was red before the flip.
- **Retrieval Mode audit and diff** (`test_retrieval_mode_draft.py`): the audited transitions start from the new default. The first change is now Agentic to Automatic, and discarding goes back to Agentic. The assertions are as strict as before.
- **Attack panel** (`test_attack_panel.py`): it passes unchanged with the Guardrail demo Agent explicitly Automatic. It failed with the default flipped and no explicit mode.
- **Live suite**: described in the Results table below.
- **End-to-end** (deferred; specs updated, linted, type-checked and listed): described in [End-to-end](#end-to-end-deferred) below.

## Tests that assumed Automatic

Once the default flipped, 43 existing tests failed (the [discovery run](#notes), before any fixture change). Each one was written about Automatic retrieval: the Retrieved Chunks table in the Trace, the Automatic preamble, no model call for an up-front fallback, or exact token counts. They now set the mode **explicitly**, and no assertion was weakened:

- **`tests/agents.py`**:
  - `AUTOMATIC` (`{"mode": "automatic"}`) is merged into the `retrieval` group of every Draft such a test saves. A Draft PUT is a whole AgentConfig, so a save without it would go back to the Agentic default.
  - `create_automatic_agent` creates an Agent and saves it Automatic.
- **Shared fixtures**, now Automatic, with docstrings that say so:
  - `ready_agent` in `test_playground.py`, which `test_playground_errors.py` and `test_agent_archive.py` also use.
  - `two_document_agent` in `test_citations_trace.py`.
  - `live_agent` and `publish_next` in `test_version_metrics.py`, which version comparison, time series, guardrail analytics, Organisation cost and retention also use. The 13-08 KPI test expects `retrieval_mode: automatic` for this fixture.
  - `live_agent_in` in `test_conversations.py`, `chatting_agent` in `test_widget_resume.py`, `scoped_agent` in `test_tag_scoping.py`, `agent` in `test_flagged_chunks.py` and `leaky_agent` in `test_canary.py`.
- **Single tests** in these files: `test_agent_revert.py`, `test_agent_versions.py`, `test_embed.py`, `test_branded_widget.py`, `test_input_guardrail_modes.py`, `test_citations_trace.py`, `test_agentic_retrieval.py::…answers_without_searching_in_automatic_mode` and `test_tool_capable_models.py`.
  - In `test_tool_capable_models.py`, the refused-save test first saves Automatic, then checks that the refused Agentic save leaves the Draft Automatic. A new Agent is Agentic even when the Default Model can't use tools: creating an Agent revalidates nothing, and the runtime's Automatic fallback covers it (13-03).
- **Unit tests** that call `run_turn` with Automatic expectations: `test_chunk_labels.py` (an `AUTOMATIC` config) and three tests in `test_prompt_assembly.py`, which pass `Retrieval(mode=RetrievalMode.AUTOMATIC)`.

**Integration of 13-07 with 13-03, 13-05, 13-06 and 13-08.** On the merged base `a6ae0d1f` the discovery run's only failures are the ones the default flip explains: each passes once its fixture sets Automatic, with nothing else changed. No integration break between the merged tickets was found, so no fix was needed beyond these fixtures.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | `mode` defaults to Agentic for new Agents | `config.py`; `test_a_new_agents_draft_has_every_group_at_its_defaults`; client regenerated, [check-client.log](check-client.log) |
| 2 | In Agentic mode the Demo model and the Naive demo model make one Knowledge Search with the Visitor's question, then answer from the first Chunk it returned | `demo.py` (`demo_search`, `_search_results`, `_naive_stream` with `naive_search`); the two `test_model_gateway.py` tests; the seed API test; [eval-live-demo.log](eval-live-demo.log) (Agentic Pass rate 91.8%, now through real Searches) |
| 3 | The seed creates one Agentic and one Automatic Agent over the same Project, each mode set explicitly; the Guardrail demo Agent is explicitly Automatic | `content.AGENTS` (`mode` required), `runner._agents`; `test_one_agentic_and_one_automatic_agent_show_the_trade_off_without_a_real_key`, `test_seeding_again_puts_back_what_was_changed`, `test_attack_panel.py`; e2e `seed.spec.ts` (new test) |
| 4 | The Five-minute demo script points out the difference between the two Agents' Traces | `README.md` step 3 (and step 5); `GLOSSARY.md` **Five-minute demo**; e2e `five-minute-demo.spec.ts` step 3 plays it |
| 5 | A live-suite test makes one real Anthropic or OpenAI Agentic reply against the seed Knowledge Base that searches and cites a Chunk | `tests/live/test_agentic_reply_live.py`, written, and skipped here without a key ([live-agentic-skip.log](live-agentic-skip.log)); see Gaps |
| 6 | Tests at the highest seam; 100% line and branch coverage | The seams above; [backend-tests.log](backend-tests.log) |
| 7 | New domain terms in `GLOSSARY.md`; ADRs updated if a decision changed | Glossary entries above; no new term, and no decision changed (ADR-0015) |

Standing criterion on Studio UI: no Studio component changed. Only the e2e specs and the generated client did. [frontend-checks.log](frontend-checks.log) shows the palette ratchet at 0.

## Results

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `cd backend && TEST_DATABASE_URL=…/studio_test_t09 TEST_REDIS_URL=redis://localhost:6379/15 uv run pytest -n 3` | **2617 passed**, 0 failed in 29 min 6 s; coverage **100.00%** (12406 statements, 1582 branches), gate reached, exit 0 | [backend-tests.log](backend-tests.log) |
| Backend lint and types | `make lint-backend` (ruff check, ruff format --check, mypy) | exit 0 (402 files) | [lint-backend.log](lint-backend.log) |
| API client drift | `make check-client` | "API client is up to date.", exit 0 | [check-client.log](check-client.log) |
| Markdown links | `make link-check` | 2815 links in 281 files, all resolve, exit 0 | [link-check.log](link-check.log) |
| Frontend | `cd frontend && pnpm test && pnpm check-embed-size && pnpm palette-ratchet && pnpm lint && pnpm typecheck` | 1112 tests in 85 files passed, 100% coverage; embed size within budget; 0 palette-class uses; lint and typecheck clean (`e2e/` included); exit 0 | [frontend-checks.log](frontend-checks.log) |
| e2e specs list | `cd frontend && pnpm e2e --list` (after `eslint` and `tsc` over `e2e/`, part of `pnpm lint` / `pnpm typecheck`) | 121 tests in 65 files | [e2e-list.log](e2e-list.log) |
| Live suite, Agentic reply | `uv run pytest -m live --no-cov -rs tests/live/test_agentic_reply_live.py` | 1 skipped: "No real Provider Credential: set SEED_CREDENTIAL_PROVIDER … and SEED_CREDENTIAL_API_KEY" | [live-agentic-skip.log](live-agentic-skip.log) |
| Attack eval, keyless live path | `make eval-live EVAL_PROVIDER=demo EVAL_MODEL=demo-chat` | PASS in every Retrieval Mode: Automatic 91.8%, Agentic 91.8% (minimum 85%); exit 0 | [eval-live-demo.log](eval-live-demo.log), [report](eval-live-demo/attack-eval-report.md) |

## End-to-end (deferred)

The Playwright stack was not run here, as instructed. The specs were updated for the new default, and they pass `eslint` and `tsc` and are listed by `pnpm e2e --list`:

- `five-minute-demo.spec.ts`: step 3 now also opens the Product FAQ. It checks "Searching: Can I return a jar of honey?", the demo answer, "Search 1: …" and the cited C1 row in "Chunks found by Search 1". Step 4 goes back to the HR helper.
- `seed.spec.ts`: a new test checks the Retrieval section of the Product FAQ (Agentic), the HR helper and the Guardrail demo (Automatic), with axe.
- `playground.spec.ts`:
  - The Agentic test is now "a new Agent is Agentic …". It no longer sets the mode through the Draft API; it checks that the new Agent's Retrieval mode radio is Agentic.
  - The Automatic tracer test switches to Automatic in the editor before asking, since it reads the Retrieved Chunks table.
- `agent-config.spec.ts`: a new Agent shows Agentic with Search limit 3. Choosing Automatic hides the limit and Agentic brings it back. The audit list gains the Agentic → Automatic event.
- `tag-scoping.spec.ts`, `reranker.spec.ts` and `retention.spec.ts` read the Retrieved Chunks table, so they set Automatic through the Draft API when they create the Agent.

**The integrated run must cover** the whole suite, and in particular:

- The specs changed here: `five-minute-demo`, `seed`, `playground`, `agent-config`, `tag-scoping`, `reranker` and `retention`.
- `demo-pages` and `attack-panel`: the Product FAQ is now Agentic on the shop pages, and the Guardrail demo is Automatic.
- `widget-accessibility`, `token-budget`, `version-kpis`, `version-comparison` and `agent-drafts`, which already set their modes explicitly.
- Every spec that creates an Agent and asks it something, which is now Agentic by default: `accessibility`, `embed`, `conversations`, `playground-errors`, `playground-instructions`, `llm-classifier`, `guardrail-analytics`, `message-feedback`, `conversation-rating`, `organisation-cost`, `time-series`, `rate-limits`, `operational-settings`, `widget-lifecycle`, `branded-widget` and `bulk-rollout`. They assert nothing Automatic-specific, so the fake model's one Search should leave them passing, but none of them has been run against the new default.

## Gaps

- **The real-provider live test was not run.** This sandbox has no Anthropic or OpenAI key, and `SEED_CREDENTIAL_PROVIDER` and `SEED_CREDENTIAL_API_KEY` are unset, so the test skips with that reason ([live-agentic-skip.log](live-agentic-skip.log)). Its plumbing was checked once with a throwaway copy that is not committed, run against `MODEL_GATEWAY=fake` and `CREDENTIAL_VERIFIER=fake` with a dummy OpenAI key. That copy seeded, asked the Agentic Product FAQ, saw a Search and a cited Chunk, and passed. The first `make test-live` run with a real key gives the real result. It needs the compose Postgres and Redis, and the provider's API reachable.
- **Playwright**: deferred to the integrated run (above).

## Notes

- **Discovery run.** The full suite ran once right after the default flip, before the fixtures were fixed: 43 failed, 2563 passed and 5 errors. The 5 errors were all in `test_demo_pages.py`. For about two minutes of that run, a second `-n 3` run was started by mistake on the same worker databases and then stopped, so those errors are not counted. `test_demo_pages.py` passes in the subset rerun (465 tests over the 30 affected files) and in the final run.
- **Seeding an existing Demo Organisation.** A re-seed sets the Drafts' modes. It does not republish, so the Product FAQ's Live Version stays as it was until `make seed-reset`. A fresh seed, and AWS's seed workflow, publish Product FAQ v1 Agentic.
