# Evidence: ticket 04-05, Reranker

Branch `ticket/04-05-reranker`, from `origin/candidate` at `f0d632d` (04-03, the only blocker, merged). The claim commit `0cdd6b8`, the first on the branch, set Status `in-progress`. No newer candidate commits existed when the checks ran.

**Status: done.** Every criterion is met and evidenced below. The gaps at the end are scope left to other tickets and best guesses recorded instead of asking.

## What was built

An Editor turns on a reranker in the Draft's Retrieval settings. The Playground then reranks every Chunk retrieval found, through the model gateway, before the Minimum Score and top-k are applied.

- **Already on candidate, from 04-07** (reused, not rebuilt):
  - `Retrieval.reranker` in `AgentConfig` (`{credential_id, model}` or `null`).
  - Validation on save: the credential must offer the model for `rerank`.
  - Registration as a Credential reference, labelled `"<Agent> (reranker)"`.
  - The Studio's Reranker picker, which lists only rerank-capable credentials.
  - From 02-03: the gateway's `reranker(credential, model)` and the `Reranker` port, with a deterministic fake (`WordOverlapReranker`) and a live Voyage adapter.
- **New in this ticket:**
  - `retrieve(…, reranker=None)` in `backend/app/retrieval/service.py`. With a reranker, every Chunk found (up to 100, in fused order) is sent to it. Candidates are then ordered by the rerank score, which becomes each Chunk's **Relevance**, and only then are the minimum score and `top_k` applied. `Candidate` and `Excluded` carry `rerank_score`. When nothing is found, the reranker isn't called (a provider would reject an empty list).
  - The Playground (`backend/app/playground/service.py`):
    - `prepare_turn` loads the Draft's reranker credential (Organisation-scoped).
    - `answer` builds it with `gateway.reranker(credential, model)` and passes it to `retrieve`.
    - The Trace and the `done` event record the reranker's relevance.
  - `GLOSSARY.md`: **Reranker** now says what an Agent's Reranker does and where in retrieval it acts. **Relevance** now says it is the Reranker's score when the Agent has one.

## Test seams

These are the [shared test seams](../../../specs/README.md#shared-test-seams) the spec names. No human was available to confirm them.

- **Retrieval interface** against real Postgres with pgvector and the deterministic embedder, on the fixture Knowledge Base, with the gateway's fake reranker. This is the spec's "the reranker reordering (fake reranker)". File: `backend/tests/integration/test_retrieval.py`.
- **API seam**: the Playground's SSE stream and the Trace endpoint, with the fake gateway adapters. File: `backend/tests/integration/test_playground.py`.
- **End-to-end** against the docker compose stack, with the fake verifier and fake gateway. No real provider or key is used. File: `frontend/e2e/tests/reranker.spec.ts` (new).

Each test was written failing first. The retrieval tests failed on the missing `reranker` argument. The Playground test failed because no reranker was built (`assert [] == ['voyage:rerank-2.5:…']`).

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | AgentConfig holds an optional reranker (a rerank-capable credential and model) | `Retrieval.reranker: ModelChoice \| None` in `backend/app/agents/config.py`, checked against the `rerank` capability by `check_draft` (`CREDENTIAL_USES` in `app/agents/validation.py`). Both come from 04-07 and are used unchanged.<br>**API tests** (`test_agent_config.py`):<br>• the full Draft round-trips `{"credential_id": voyage, "model": "rerank-2.5-lite"}`;<br>• a non-rerank credential gives "This credential can't be used for rerank.";<br>• an unoffered model gives "Voyage AI doesn't offer rerank-1 for rerank.".<br>**This ticket:** `test_the_drafts_reranker_chooses_the_chunks_the_model_is_given` saves a Draft with a Voyage `rerank-2.5` reranker (200).<br>**E2E:** `reranker.spec.ts` picks "Search Voyage (Voyage AI)" and `rerank-2.5` in the editor's Reranker group, and the Draft autosaves (200, "All changes saved", axe clean). |
| 2 | Candidates are reranked before the threshold and top-k are applied (tested with a fake reranker) | **Code:** `_rerank` and `retrieve` in `app/retrieval/service.py`.<br>**Retrieval tests** (`test_retrieval.py`, fake `WordOverlapReranker`):<br>• `test_the_reranker_reorders_the_candidates_before_top_k_is_applied`: semantic-only, `top_k=1`. Without the reranker PRODUCT is excluded `outside_top_k`. With it, PRODUCT is the one candidate, with `rerank_score` = relevance = 2/5 and an unchanged fused score. The other 5 are `outside_top_k` with rerank score 0.<br>• `test_the_minimum_score_is_applied_to_the_reranked_candidates`: `min_score=0.3`. Without the reranker there are no candidates (the fallback would fire). With it, PRODUCT passes and the rest are `below_min_score` (relevance 0). At `min_score=0.5` nothing passes.<br>• `test_the_candidates_are_ordered_by_the_rerankers_scores`: keyword search doesn't rank PARKING first; reranked, PARKING (2/4) leads and three Chunks at 1/4 follow, ranks 1–4.<br>• `test_the_reranker_isnt_asked_when_nothing_is_found`<br>**API test** (`test_playground.py::test_the_drafts_reranker_chooses_the_chunks_the_model_is_given`): the gateway builds `voyage:rerank-2.5` with the credential's own secret. The model is given only `[C1] product.txt`, which differs from the Chunk chosen before the reranker was set. The `done` event and Trace show relevance 0.4, and the excluded Chunks are `outside_top_k` with relevance 0.<br>**E2E:** with top-k 1, the Trace's Retrieved Chunks table shows C1 `product.txt` with relevance `0.400` and `leave.txt` left out with `0.000`. |
| 3 | The reranker credential is registered as a reference | `agent_references` (`app/agents/validation.py`, 04-07) covers `retrieval.reranker`.<br>**API test:** `test_agent_config.py::test_credentials_an_agent_uses_cant_be_deleted` gives 409 with `{"kind":"agent","id":…,"name":"HR helper (reranker)"}`.<br>**E2E (this ticket):** `reranker.spec.ts` sets the reranker in the editor. Deleting the Voyage credential then gives 409 with exactly `[{kind: "agent", id: agentId, name: "Support helper (reranker)"}]`. |
| 4 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | See the seams above.<br>• Backend gate (`fail_under = 100`, branch on): **100%**, 6721 statements, 714 branches, 0 missed ([backend-tests.log](backend-tests.log)).<br>• Frontend Vitest gate: 100% ("No files with missing coverage") ([frontend-tests.log](frontend-tests.log)). No Studio source changed. |
| 5 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md`: **Reranker** (an Agent's Reranker, where it acts, a Credential reference) and **Relevance** (the Reranker's score when there is one) are updated. No new term was needed. No ADR changed: ADR-0001 (hybrid search with RRF) still holds, the reranker is an optional step after fusion as the spec lays out, and the call goes through the model gateway. |

## Results

All runs are local and sequential on a machine shared with five other tickets. GitHub Actions is down; the user authorised merging on local results.

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `make test-backend` against `rag0405-pg` (pgvector 0.8.1-pg16), `rag0405-redis` and `rag0405-rustfs` | **1451 passed**, 7 deselected (live); coverage 100% lines and branches | [backend-tests.log](backend-tests.log) |
| Frontend tests + coverage gate | `make test-frontend` | **38 files, 465 tests passed**; 100% | [frontend-tests.log](frontend-tests.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc); `make lint-frontend` rerun after the e2e spec fix | exit 0 both | [lint.log](lint.log), [lint-frontend-rerun.log](lint-frontend-rerun.log) |
| API client drift | `make check-client` | "API client is up to date." (no API schema change) | [client-drift.log](client-drift.log) |
| Security | gitleaks over this branch's commits; `make audit` (pip-audit, pnpm audit) | no leaks, no known vulnerabilities | [security.log](security.log) |
| Images | `build.sh` (sandbox `make images`) at `0978400` | both built | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` (project `rag0405`, ports 47xxx) | Final run: **55 passed**, exit 0, including `reranker.spec.ts`. Earlier attempts below. | [e2e.log](e2e.log), [e2e-attempt1.log](e2e-attempt1.log), [e2e-attempt2.log](e2e-attempt2.log), [e2e-attempt3.log](e2e-attempt3.log) |
| Infra | not run | this branch changes nothing under `infra/` | |

**End-to-end runs:**

- **Attempt 1:** 54 passed, 1 failed. The failure was the new `reranker.spec.ts` itself: it waited for a save after setting the minimum relevance to 0, which is already the default, so no save came. Fixed in `f011c49`: the spec now checks the field shows 0.
- **Attempt 2:** the reranker spec passed (33.6 s), but four unrelated specs (members, organisation switcher, require MFA, projects) timed out at 30 s with load average 35. All four passed in attempt 1.
- **Attempt 3:** 54 passed, 1 failed. An unrelated `auth.spec.ts` check timed out after 5 s (the Sign in heading) under shared-machine load; it passed in attempts 1 and 2.
- **Final run:** **55 of 55 passed**, exit 0, at `f011c49` ([e2e.log](e2e.log)).

The images were built at `0978400`. The commits after it change only `reranker.spec.ts`, which Playwright runs on the host, and this folder.

## Gaps and best guesses

- **Relevance with a reranker (best guess, recorded instead of asking).** The criterion says reranking comes before the threshold, so the threshold must see the reranked result. So when a reranker runs, a Chunk's Relevance is the reranker's score (both are 0–1, and a rerank model's judgement is the better one). Candidates are ordered by it. Without a reranker nothing changes. The Editor's Minimum Score therefore means "rerank score" for an Agent with a reranker. The glossary says so.
- **What is reranked:** every Chunk found by either search (at most 50 each), not just the first top-k. This lets the reranker lift a Chunk fusion ranked low, which is the point of the feature.
- **The Trace keeps its columns.** Score is still the fused score; Relevance shows the rerank score. `rerank_score` lives on the retrieval result but isn't persisted or shown separately. That would need a migration and a Trace drawer change, and 04-06/07-01 own those. Its value is already visible as Relevance.
- **Reranker provider errors** (bad key, outage) are raised like chat-model errors are today. Typed error events in the Playground stream are ticket 04-08.
- **Bedrock reranking:**
  - Accepted and validated (`cohere.rerank-v3-5:0`), and the fake gateway answers for it.
  - The live Bedrock rerank client was left unbuilt by 02-02/02-03 (`app/gateway/live.py`), and IAM-role credentials can't build one (`UnsupportedCredentialError`), as for chat. That client is outside this ticket's criteria.
  - The Voyage live reranker exists. Nothing live was called here: no real keys or paid rerank calls.
- **Sandbox limits:**
  - Images were built with `WITH_PDF=false BUNDLE_MODELS=false` and the egress proxy CA (`build.sh`), as earlier tickets did.
  - E2E ran on moved ports (`compose.sandbox.yml`).
  - The `rag0405-*` containers, the compose stack, the `rag-agent-studio/*:0405` images and their build cache were removed afterwards.
