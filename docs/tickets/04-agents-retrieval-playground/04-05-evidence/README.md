# Evidence: ticket 04-05, Reranker

Branch `ticket/04-05-reranker`, from `origin/candidate` at `f0d632d` (04-03, the only blocker, merged). The claim commit `0cdd6b8`, the first on the branch, set Status `in-progress`. `origin/candidate` was merged in five times as it moved:

- `00f8214` (10-01) at `609c87b`, with no conflicts.
- `a123fa1` (03-11) and `dc9a3b9` (04-04 Tag scoping) at `3f5ad31` and `e8607ef`. 04-04 conflicted in `retrieval/service.py` and `test_retrieval.py`: both features kept. Tag scoping limits the two searches before fusion, and the reranker then reranks only the in-scope Chunks. `outside_tags` exclusions are never reranked and carry no rerank score. New test: `test_the_reranker_sees_only_the_chunks_inside_the_tags`.
- `198d5e6` (04-08 Playground errors) at `7c56674`. It conflicted in `playground/service.py`. The reranker is built after the chat model, and a gateway failure building it (say `UnsupportedCredentialError`) ends the turn with a typed `model_unavailable` error naming the rerank model. New test: `test_playground_errors.py::test_a_reranker_the_gateway_cant_build_is_unavailable`.
- `f3bd85f` (03-10 Re-embed) at `8a7df8e`, with no conflicts.
- `7dcd64d` (04-09 Agent archive and delete) at `8e32719`. An import conflict in `playground/service.py`: both `ModelChoice` (the reranker) and `active_agent` (04-09) are kept.

A reranker that raises one of 04-08's `PROVIDER_ERRORS` while it ranks is caught by 04-08's `run_turn` handler.

Every check below was rerun on the final merged tree `8e32719`.

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
| 4 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | See the seams above.<br>• Backend gate (`fail_under = 100`, branch on): **100%**, 7594 statements, 870 branches, 0 missed ([backend-tests.log](backend-tests.log)).<br>• Frontend Vitest gate: 100% ("No files with missing coverage") ([frontend-tests.log](frontend-tests.log)). No Studio source changed. |
| 5 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md`: **Reranker** (an Agent's Reranker, where it acts, a Credential reference) and **Relevance** (the Reranker's score when there is one) are updated. No new term was needed. No ADR changed: ADR-0001 (hybrid search with RRF) still holds, the reranker is an optional step after fusion as the spec lays out, and the call goes through the model gateway. |

## Results

All runs are local and sequential, on the merged tree `8e32719`, on a machine shared with five other tickets (load average 13–35). GitHub Actions is down; the user authorised merging on local results.

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `make test-backend` against `rag0405-pg` (pgvector 0.8.1-pg16), `rag0405-redis` and `rag0405-rustfs` | **1609 passed**, 7 deselected (live); coverage **100%** lines and branches (7594 statements, 870 branches) | [backend-tests.log](backend-tests.log) |
| Frontend tests + coverage gate | `make test-frontend` | **39 files, 491 tests passed**; 100% ("No files with missing coverage") | [frontend-tests.log](frontend-tests.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc) | exit 0 | [lint.log](lint.log) |
| API client drift | `make check-client` | "API client is up to date." (no API schema change) | [client-drift.log](client-drift.log) |
| Security | gitleaks over this branch's commits; `make audit` (pip-audit, pnpm audit) | no leaks, no known vulnerabilities | [security.log](security.log) |
| Images | `build.sh` (sandbox `make images`) at `8e32719` | both built | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` (project `rag0405`, ports 28xxx), on images from `8e32719` | **62 passed**, exit 0, including `reranker.spec.ts` | [e2e.log](e2e.log) |
| Infra | not run | this branch changes nothing under `infra/` | |

**Earlier end-to-end runs** (kept for honesty; none failed for a reason in this ticket's code):

- [e2e-attempt1.log](e2e-attempt1.log), at `0978400`: 54 passed, 1 failed. The failure was the new `reranker.spec.ts`. It waited for a save after setting the minimum relevance to 0, which is already the default, so no save came. Fixed in `f011c49`: the spec now checks the field shows 0.
- [e2e-attempt2.log](e2e-attempt2.log) and [e2e-attempt3.log](e2e-attempt3.log), at `f011c49`: the reranker spec passed. Four and then one unrelated spec (members, organisation switcher, require MFA, projects; then auth) timed out under load average 23–35.
- [e2e-premerge-f011c49.log](e2e-premerge-f011c49.log): 55 of 55 passed before the candidate merge.
- On the merged tree:
  - [e2e-merged-portclash.log](e2e-merged-portclash.log): the stack failed to start because host port 47300 was briefly taken.
  - [e2e-merged-attempt1.log](e2e-merged-attempt1.log): 55 passed. `members.spec.ts` and `projects.spec.ts` timed out on 5 s toasts under load. Both passed in the next run (57 of 57 at `609c87b`).
- After the later candidate merges: 58 of 58 passed at `3f5ad31` and 59 of 59 at `e8607ef`. At `7c56674` the first image build and stack start failed with "no space left on device" on the shared disk (other tickets' images). The images and e2e were rerun once space was free. That run ([e2e-7c56674-attempt1.log](e2e-7c56674-attempt1.log)) had 59 passed and 1 failed: `projects.spec.ts` timed out on a 5 s toast under load average 17–18, the same flake as before. The next run passed 60 of 60. One Vitest run at `e8607ef` also hit ENOSPC after all 471 tests passed; it passed on rerun.
- At `8a7df8e` (after merging 03-10): two stack starts failed because host port 47300 was briefly taken ([e2e-8a7df8e-portclash1.log](e2e-8a7df8e-portclash1.log), [e2e-8a7df8e-portclash2.log](e2e-8a7df8e-portclash2.log)). The next run passed 61 of 61.
- At `8e32719` (after merging 04-09):
  - [backend-tests-8e32719-attempt1.log](backend-tests-8e32719-attempt1.log): 1608 passed, 1 failed. `test_logging.py::test_the_api_server_writes_only_json_lines` couldn't connect to the API server subprocess it starts, under load. The suite's next run, [backend-tests.log](backend-tests.log), passed all 1609.
  - [e2e-8e32719-portclash.log](e2e-8e32719-portclash.log) and [e2e-8e32719-portclash2.log](e2e-8e32719-portclash2.log): the stack couldn't start. Another ticket's containers held 47832, then an ephemeral connection held 49800. The sandbox ports moved to 28xxx, below the ephemeral range. The next run, [e2e.log](e2e.log), passed 62 of 62.

## Gaps and best guesses

- **Relevance with a reranker (best guess, recorded instead of asking).** The criterion says reranking comes before the threshold, so the threshold must see the reranked result. So when a reranker runs, a Chunk's Relevance is the reranker's score (both are 0–1, and a rerank model's judgement is the better one). Candidates are ordered by it. Without a reranker nothing changes. The Editor's Minimum Score therefore means "rerank score" for an Agent with a reranker. The glossary says so.
- **What is reranked:** every Chunk found by either search (at most 50 each), not just the first top-k. This lets the reranker lift a Chunk fusion ranked low, which is the point of the feature.
- **The Trace keeps its columns.** Score is still the fused score; Relevance shows the rerank score. `rerank_score` lives on the retrieval result but isn't persisted or shown separately. That would need a migration and a Trace drawer change, and 04-06/07-01 own those. Its value is already visible as Relevance.
- **Reranker provider errors** (bad key, outage) now end the turn with 04-08's typed error events. A reranker the gateway can't build names the rerank model. An error raised while reranking names the model the provider error reports, or else the chat model (04-08's handler), which is a best guess left as is.
- **Bedrock reranking:**
  - Accepted and validated (`cohere.rerank-v3-5:0`), and the fake gateway answers for it.
  - The live Bedrock rerank client was left unbuilt by 02-02/02-03 (`app/gateway/live.py`), and IAM-role credentials can't build one (`UnsupportedCredentialError`), as for chat. That client is outside this ticket's criteria.
  - The Voyage live reranker exists. Nothing live was called here: no real keys or paid rerank calls.
- **Sandbox limits:**
  - Images were built with `WITH_PDF=false BUNDLE_MODELS=false` and the egress proxy CA (`build.sh`), as earlier tickets did.
  - E2E ran on moved ports (`compose.sandbox.yml`, 28xxx).
  - Unrelated e2e specs time out under shared-machine load (see Results). Not changed here: they belong to other tickets.
  - The `rag0405-*` containers, the compose stack, the `rag-agent-studio/*:0405` images and their build cache were removed afterwards.
