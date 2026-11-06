# Evidence: ticket 04-04, Tag scoping

Branch `ticket/04-04-tag-scoping`, from `origin/candidate` at `c3e8db7` (its blockers, 04-03 Hybrid retrieval and fallback and 03-06 Tags, merged and `done`). The claim commit, the first on the branch, set Status `in-progress`.

**Status: done.** Every criterion is met and evidenced below. Gaps and best guesses are at the end.

## What was already on candidate

04-07 (Full AgentConfig editor) had already added the storage and validation half of Tag scoping, so this ticket builds on it rather than re-doing it:

- `Retrieval.tag_ids` in `AgentConfig` (`backend/app/agents/config.py`, unique, at most `TAGS_MAX`), the Studio's **Tag scoping** checkboxes in the Agent editor (`DraftEditor.tsx`);
- `validate_draft` refusing Tag IDs that aren't the Agent's Project's (`backend/app/agents/validation.py`, `unknown_tag`);
- `delete_tag` taking the Tag out of every Draft scoped to it (`backend/app/tags/service.py`, `_unscope_drafts`).

What was missing: retrieval ignored `tag_ids`, and deleting a Tag gave no warning.

## What was built

- **Retrieval** (`backend/app/retrieval/service.py`): with Tags, semantic and keyword search are both limited to Documents carrying at least one of the Tags (`Document.id IN (SELECT document_id FROM document_tags WHERE tag_id IN …)`), before fusion, so out-of-scope Chunks never take a place in the candidate pool or the ranking. The query is embedded and parsed into terms once (`_Searches`). So the Trace can show what scoping left out (spec story 28), the same searches also run over the Project's other Documents (none of the Tags, untagged included), fused on their own, and the best `top_k` are returned as Excluded Chunks with the new reason `outside_tags`. No Tags searches every Document, as before.
- **Trace** (`playground/api.py` reuses `ExcludedReason`, so OpenAPI and the generated client gain `outside_tags`); the Studio's Trace drawer labels it "Excluded: outside the Agent's Tags".
- **Tag deletion warning**: `TagOut` gains `agents` (`[{id, name}]`, by name) — the Project's Agents whose Draft is scoped to the Tag (`_scoped_agents` in `tags/service.py`, one query for the list, filtered by `@>` for one Tag). In the Tags panel, choosing **Delete** on such a Tag shows, before confirming: "2 Agents are limited to HR: HR helper, Onboarding. Deleting it takes it out of their Drafts; an Agent left with no Tags searches every Document." A Tag no Agent uses shows no warning.
- API client regenerated (`make gen-client`). `GLOSSARY.md`: new **Tag scoping** entry; **Excluded Chunk** gains the third reason.

## Test seams

The [shared test seams](../../../specs/README.md#shared-test-seams), as spec 04's Testing Decisions name them (no human was available to confirm seams; these are the pre-agreed ones):

- **Retrieval through its interface** against real Postgres/pgvector with the deterministic embedder on the fixture Knowledge Base (`backend/tests/integration/test_retrieval.py`), as spec 04 asks for Tag scoping.
- **API seam** (`backend/tests/integration/test_tag_scoping.py`, `test_agent_config.py`): Playground and Tags routes in-process, a `FunctionModel` as the chat model.
- **Network seam** (`frontend/apps/studio/src/projects/DocumentTags.test.tsx`, `AgentPage.test.tsx`), MSW.
- **End-to-end** (`frontend/e2e/tests/tag-scoping.spec.ts`) against the docker compose stack with the fake chat model and fake embedder, plus axe.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | AgentConfig holds Tag IDs, and retrieval filters by them | **Code:** `Retrieval.tag_ids` (config.py, from 04-07); `retrieve` → `_tag_scope(tag_ids, inside=True)` applied to both searches.<br>**Tests:**<br>• `test_tag_scoping_searches_only_documents_with_one_of_the_tags` (retrieval): HR = leave+expenses, Policies = rules+leave, Sales = none. The product question, scoped to HR, returns only leave and expenses although the product Chunk is the best keyword match; HR+Policies returns leave, expenses and rules, leave once; Sales (no Documents) finds nothing; no Tags finds all six.<br>• `test_chunks_outside_the_tags_are_reported_as_excluded` (retrieval): with `top_k=2`, exactly two `outside_tags` exclusions, the product Chunk first with relevance 3/6, best first, none from HR Documents, none also a candidate; with `top_k=1` the product Chunk is the one, fused score 1.<br>• `test_agents_sharing_a_project_are_given_only_their_tags_material` (API): three Agents on one Project — HR helper (HR), Sales helper (Sales), Front desk (no Tags) — ask the product question in the Playground; the Traces show HR helper given only leave+expenses with the product Chunk first among three `outside_tags`; Sales helper given only the product; Front desk given the product first and nothing `outside_tags`.<br>• Network seam: `the Trace drawer shows … every Chunk retrieved` now includes a row "Excluded: outside the Agent's Tags".<br>• E2E `tag-scoping.spec.ts`: the Editor ticks **HR** under Tag scoping (autosaved), asks about SKU-4471; the only source is `C1 leave-policy.md`; the Trace row for `price-list.md` reads "Excluded: outside the Agent's Tags"; axe passes. |
| 2 | Unknown Tags, or Tags from another Project, are rejected | **Code:** `validate_draft` (validation.py, from 04-07), 422 `unknown_tag` "Choose Tags from this Project." per bad index.<br>**Tests:** `test_tags_must_belong_to_the_agents_project` (API, `test_agent_config.py`): own Tag accepted, a Tag of another Project and a random UUID each refused at their index; `test_out_of_range_settings_are_refused_with_where_and_why` includes `retrieval.tag_ids = ["not-a-uuid"]` (422); duplicates are collapsed. Retrieval itself also only matches the Project's Documents, so even a stale Tag ID (e.g. a Tag deleted after a future published Version) matches nothing rather than leaking another Project's material. |
| 3 | Deleting a Tag that Agents reference warns which Agents use it | **Code:** `TagOut.agents` (tags/api.py, service.py `_scoped_agents`); `TagsPanel.tsx` `scopedAgentsWarning`, shown as an alert in the delete confirmation.<br>**Tests:**<br>• `test_each_tag_lists_the_agents_scoped_to_it_so_deleting_it_can_warn` (API): HR lists HR helper and Onboarding (by name), Policies lists HR helper, an unused Tag and a new Tag list none, a renamed Tag keeps its Agents, a same-named Tag in another Project doesn't leak its Agent; after deleting HR the remaining Tags' lists are right.<br>• `test_deleting_a_tag_takes_it_out_of_every_draft_that_scoped_to_it` (API, 04-07): the Draft keeps its other Tags and re-saves.<br>• `deleting a Tag that Agents are scoped to warns which Agents use it` (network seam): exact warning for 2 Agents and for 1 Agent; no warning for an unused Tag; "Keep it" sends nothing; confirming deletes.<br>• E2E: Delete HR shows "1 Agent is limited to HR: HR helper. …", axe passes, and after confirming the Agent's Draft has no Tags. |
| 4 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | **Met.** Each new behaviour is tested at the highest seam that sees it (listed under Test seams and in rows 1-3): retrieval through `retrieve` against real Postgres/pgvector, the Playground and Tags HTTP API in-process, the Studio through MSW, and end-to-end through the browser (`tag-scoping.spec.ts`). Coverage: backend 100.00% line+branch ([backend-tests.log](backend-tests.log), "Required test coverage of 100.0% reached"), frontend 100% statements/branches/functions/lines ([frontend-tests.log](frontend-tests.log)); both gates are enforced by the Make targets and exited 0. |
| 5 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md`: **Tag scoping** (new), **Excluded Chunk** (adds "outside the Agent's Tags"). No ADR decision changed (ADR-0001's hybrid search is unchanged; scoping is a filter inside it). |

## Results

Rerun after merging `origin/candidate` at `a123fa1` (03-11 Permanent Project deletion, after 10-01 Seed foundation and 02-06 Theme images; clean merges, no conflicts). All from a fresh `git clone` of the branch at `45b838a` (the merge commit; later commits only touch this evidence folder), run one at a time by [`run-checks.sh`](run-checks.sh) on 2026-11-06. Backend tests used throwaway `rag0404-pg/redis/rustfs` containers; e2e used the compose stack (`-p rag0404`) with the images [`build.sh`](build.sh) built and [`compose.sandbox.yml`](compose.sandbox.yml) / [`e2e.env`](e2e.env). The first run of the code commit `1520cb1` (before the merges) was also all green: 1389 backend tests at 100%, 53 e2e.

| Check | Command | Exit | Summary | Log |
|---|---|---|---|---|
| Install | `make install` | 0 | backend + frontend dependencies installed from lockfiles | [install.log](install.log) |
| Lint + typecheck | `make lint` | 0 | ruff: all checks passed; ruff format: 264 files formatted; mypy: no issues in 264 files; eslint `--max-warnings=0` clean; `tsc` clean | [lint.log](lint.log) |
| Frontend tests, 100% gate | `make test-frontend` | 0 | 38 files, 471 tests passed; Statements 2329/2329, Branches 1391/1391, Functions 896/896, Lines 2062/2062 (100%) | [frontend-tests.log](frontend-tests.log) |
| API client drift | `make check-client` | 0 | "API client is up to date." | [client-drift.log](client-drift.log) |
| Security | `gitleaks git origin/candidate..HEAD`; `make audit` | 0, 0 | no leaks in 3 commits; pip-audit and pnpm audit: no known vulnerabilities | [security.log](security.log) |
| Backend tests + coverage | `make test-backend` | 0 | 1507 passed, 7 deselected (live) in 37m38s; line+branch coverage 100.00% (7110 statements, 798 branches, 0 missed); includes `test_retrieval.py` (12), `test_tag_scoping.py` (2), `test_agent_config.py` (33) | [backend-tests.log](backend-tests.log) |
| Images | `build.sh` | 0 | api and studio images built | [images.log](images.log) |
| E2E (full suite, incl. `tag-scoping.spec.ts`) | `CI=1 make e2e` | 0 | 58 passed (4.2m); `tag-scoping.spec.ts:18` passed (16.7s) | [e2e.log](e2e.log) |

Flakes seen on the way, under a load average of 18-30 on the shared 4-CPU machine, none in this ticket's code and none in the final run: an e2e run at `1613b29` failed `members.spec.ts` and `mfa.spec.ts` on 30 s timeouts (3 more flaky); a backend run at `218a6c9` passed all tests but missed `app/api/health.py` 118-119 (99.96%), because the worker-health failed-task test reached its deadline before the worker replied. Both passed on rerun.

## Gaps and best guesses

- **Best guesses** (no human available to ask):
  - Several Tags are an OR (a Document with any one of them is searched), as the config comment and the Agent editor's hint ("Only search Documents with one of these Tags") already said.
  - "Warns" is a warning in the Studio before the Editor confirms, not an API refusal: the API's DELETE still succeeds (the Tag is taken out of the Drafts, as 04-07 built), and `TagOut.agents` is the data the warning shows. The warning also says the consequence that matters: an Agent left with no Tags searches every Document.
  - Out-of-scope Chunks for the Trace: the best `top_k` by their own fused score (not every Chunk in the Project), so the Trace stays readable; this costs one extra pair of searches only when an Agent has Tags. They are never given to the model and never affect the fallback.
  - Archived Agents are listed among a Tag's Agents like any other (Agent archive arrives in 04-09; no archived flag is shown yet).
  - Published Versions (spec 05) are snapshots: deleting a Tag doesn't rewrite them, and a stale Tag ID simply matches no Document.
- **Sandbox limits** (as earlier tickets): images built with `WITH_PDF=false BUNDLE_MODELS=false`, e2e with `EMBEDDER=fake`. The live suite and Trivy image scan were not run (no change to models or image dependencies). No dependencies added. GitHub Actions is down; the user authorised merging on local results.
