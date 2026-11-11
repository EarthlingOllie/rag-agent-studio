# Evidence: ticket 05-05, Bulk publish, bulk revert and Instructions rollout

Branch `ticket/05-05-bulk-publish-revert`, from `origin/candidate` at `d522c93` (05-03, Revert via Live History, merged as #50). The claim commit `f30ac87`, the first on the branch, set Status `in-progress`. The feature is `c5376a5`; `origin/candidate` had not moved when the checks ran. The commit after it adds this folder and sets Status `done`. This ticket adds no migration: the `bulk_publish` and `bulk_revert` actions and the Live History `bulk_operation_id` column came with 05-02.

**Status: done.** Every criterion is met and evidenced below. The gaps at the end are scope left to later tickets on purpose, plus what this sandbox can't run.

## What was built

- **Bulk module** (`backend/app/agents/bulk.py`, rule written in the module docstring):
  - **Bulk publish** builds each Agent's new Version from its **Live Version's config** plus the chosen Instructions Version, never from the Draft (ADR-0003). Never-published Agents are skipped ("Never published, so it has no Live configuration to build from. Publish it from its page first."), and so are Agents already Live with that Instructions Version ("Already Live with Instructions vN."). The note defaults to "Bulk published with Instructions vN".
  - **Bulk revert** applies the 05-03 Live History rule to each Agent. "Nothing to revert to" is a skip; a target whose credential is gone is a failure.
  - **Each Agent gets its own transaction**, under its row lock (`SELECT … FOR UPDATE`). The bulk module commits after each Agent, and rolls back only that Agent on any error. The result has one outcome per Agent, in request order (a repeated ID once): `succeeded` (with the new Live Version and pinned Instructions), `skipped` with the reason, or `failed` with the reason (archived Agent, "Not found." for an ID outside the Project or Organisation, or a generic failure for an unexpected error).
  - **Bulk operation ID:** a new UUID per bulk action. It is written on every Live History entry (`bulk_publish` / `bulk_revert`), on every per-Agent Audit Event (`agent.bulk_published` / `agent.bulk_reverted`, `after.bulk_operation_id`), and on one summary Audit Event on the Project (`project.agents_bulk_published` / `project.agents_bulk_reverted`) with the succeeded/skipped/failed counts.
  - **Rollout summary:** the Project's active Agents with their Live Version, the Instructions Version it pins, whether the Draft differs from the Live Version (`has_draft_changes`), whether the Agent is **behind** (live, but not pinning the Current Version), and the `behind` count.
  - `app/agents/versions.py`: publish and revert were split into `make_live` and `step_back` (lock and commit stay with the caller), so the single and bulk actions share one code path. Their behaviour is unchanged (05-02's and 05-03's tests pass as they were).
- **API** (`backend/app/agents/bulk_api.py`, Editors and Owners, scoped by the one policy dependency):
  - `POST …/projects/{id}/agents/bulk-publish` (`bulkPublishAgents`): `agent_ids` (1–200), `instructions_version_id`, optional `note`. 404 for an unknown Project, 409 for an archived Project, 422 for an Instructions Version that isn't the Project's.
  - `POST …/projects/{id}/agents/bulk-revert` (`bulkRevertAgents`): `agent_ids`. 404 / 409 as above.
  - `GET …/projects/{id}/instructions/rollout` (`getInstructionsRollout`).
  - `POST …/instructions/revert` now also returns `reverted_from` and `bulk_revert_candidates`: the active Agents whose Live Version pins the reverted Version.
- **Studio:**
  - `BulkRollout.tsx` / `bulk.ts`:
    - **Rollout dialog:** publishing Instructions opens "Roll out Instructions vN". Every Agent that can take it is pre-selected. Never-published Agents and Agents already on vN are listed but disabled, with the reason. Agents with Draft changes get the badge "Unpublished Draft changes (not included)". "Publish to N Agents" shows the per-Agent results.
    - **"N Agents behind":** the Instructions tab has an Agents section with "N Agents behind the Current Version (vN)", a table of each Agent's Live Version and pinned Instructions ("(behind)"), and a "Roll out vN…" button that opens the same dialog.
    - **Bulk-revert offer:** after reverting the Instructions, a dialog "Revert the Agents on Instructions vN?" lists the candidates pre-selected, then shows the results.
  - `AgentsTab.tsx`: the active Agent list of an active Project gets a checkbox per Agent. "Revert selected (N)" asks for confirmation, then shows the per-Agent results and clears the selection.
- The **generated API client** was regenerated (`make gen-client`).

## Test seams

These follow the [shared test seams](../../../specs/README.md#shared-test-seams) and the spec's Testing Decisions. They were not confirmed with a human; they are the seams 05-02 and 05-03 used for the same module.

- **API seam:** `backend/tests/integration/test_bulk_versions.py` (16 tests, 20 cases), in process against real Postgres and Redis. It asserts on HTTP responses and what reads back through the API (Agents, Versions, Live History, Audit Events, the rollout summary, the Instructions revert response). There are two exceptions:
  - What a Visitor is served goes through the serving module with the echoing `FunctionModel`, as in 05-02 and 05-03, because there is no Visitor route until 06-01.
  - The forced failure monkeypatches `app.audit.record` to raise for one Agent. That is the "forced failure on one Agent" the spec asks for.
  - `test_tenant_isolation.py` adds the three routes (another Organisation gets 404, unauthenticated requests get 401, Editors are allowed). `test_openapi.py` lists the operation IDs. The two Instructions revert tests that compare the whole response now include the new fields.
- **Network seam:** `frontend/apps/studio/src/projects/BulkRollout.test.tsx` (14 tests) and `AgentsTab.test.tsx` (3 new tests), with the `fakeBulkApi` MSW fake (`src/test/bulk.ts`). The Instructions revert fake now returns `reverted_from` and the candidates.
- **End-to-end seam:** `frontend/e2e/tests/bulk-rollout.spec.ts`, Playwright against the docker compose stack, with axe. It runs the spec's scenario.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Bulk publish uses Live config plus the chosen Instructions Version, never the Draft, and skips Agents that have never been published | **API:**<br>• `test_bulk_publish_builds_from_the_live_config_and_the_chosen_instructions`: the Draft is edited to "Unreviewed." after v1 ("Live prompt."). Bulk publishing Instructions v2 gives v2 with exactly v1's config, pinning Instructions v2. The echo model receives "Second rules." and "Live prompt.", attributed to v2, and the Draft still holds "Unreviewed.".<br>• `test_bulk_publish_skips_never_published_agents_and_ones_already_on_the_version`: the never-published Agent is skipped with the reason and gets no Version.<br>• `test_bulk_publish_names_the_instructions_version_when_no_note_is_given`<br>• `…_refused_for_an_unknown_instructions_version_or_an_archived_project`<br>• `…_needs_one_to_200_agents_and_a_short_note`<br>**Studio:** the dialog lists the never-published Agent disabled with "Never published: not included…".<br>**E2E:** Agent B's Draft edit is not shipped (B keeps one Version until it is rolled out from Live), and Agent A's v2 pins Instructions v2. |
| 2 | Each Agent is processed in its own transaction, with a result per Agent | **API:**<br>• `test_a_failure_on_one_agent_leaves_the_others_committed`: a forced failure on the middle Agent after its Version is written. First and Last are committed on v2; Broken is unchanged (Live v1, one Version, one Live History entry, no bulk Audit Event); its result is `failed` with the generic reason.<br>• `test_bulk_results_report_agents_that_failed_and_why`: archived Agent, other Organisation, other Project, unknown ID and a duplicate, in request order.<br>• `test_bulk_revert_reports_failures_per_agent`: archived, unknown, gone credential (`failed`, still Live v2) and success.<br>**Studio:** the "Results" list for succeeded, skipped and failed; "Unknown Agent" when there's no name; whole-request refusals. |
| 3 | Agents with Draft changes are badged in the dialog | **API:** the rollout's `has_draft_changes` is true only for the Agent whose Draft was edited after publishing (`test_the_rollout_shows_each_agents_pinned_instructions_and_how_many_are_behind`).<br>**Studio:** "publishing Instructions opens the rollout dialog…": Benefits FAQ shows "Unpublished Draft changes (not included)".<br>**E2E:** Agent B's row carries the badge. |
| 4 | Publishing Instructions opens the dialog with Agents pre-selected, and "N Agents behind" is shown | **Studio:**<br>• the dialog opens after publish, with eligible Agents checked and others disabled<br>• deselecting<br>• "2 Agents behind the Current Version (v2)." and the per-Agent table<br>• singular and zero cases; no rollout button on an archived Project<br>• "Roll out v2…" opens the dialog<br>• empty, loading and error states<br>**API:** rollout `behind` = 3, with the per-Agent Live Version and pinned Instructions, never-published Agents not behind and archived Agents left out; readable on an archived Project; 404 for an unknown Project.<br>**E2E:** "0 Agents behind (v1)" → publish v2 in the Studio → dialog with A and B checked → uncheck B → "1 Agent behind the Current Version (v2)." with B "(behind)". |
| 5 | Reverting Instructions offers a bulk revert of the Agents pinned to the reverted Version | **API:** `test_reverting_instructions_returns_the_agents_pinned_to_the_reverted_version`: the revert returns `reverted_from` v2 and only the active Agent Live on v2. The archived one and the one held on v1 are left out. Taking the offer puts it back on Instructions v1, and `behind` is 0.<br>**Studio:** the offer dialog (pre-selected, deselect, results, Done), declining it, its progress and refusals, and no offer when no Agent is pinned.<br>**E2E:** v2 is rolled out to both Agents, then the Instructions are reverted. The offer lists "Agent A (Live v3)" and "Agent B (Live v2)", and after "Revert 2 Agents" both are Live with Instructions v1. |
| 6 | The Agent list supports multi-select bulk revert | **API:** `test_bulk_revert_steps_each_agent_back_along_its_live_history`: per-Agent results; reverting again walks further back; no Version is created; `test_a_single_revert_after_a_bulk_publish_follows_it_back`.<br>**Studio:** `AgentsTab.test.tsx`: select, deselect, confirm, Cancel, "Yes, revert 2 Agents", results, the selection cleared, a whole-request refusal, and no checkboxes for archived Agents or an archived Project.<br>**E2E:** Agents tab → "Select Agent A" → "Revert selected (1)" → "Agent A — Done: Reverted to v1 with Instructions v1"; the API reports A Live v1 pinning Instructions v1 (the spec's "it serves v1 again"). |
| 7 | A bulk operation ID is recorded on Live History and Audit Events | **API:** `test_the_bulk_operation_id_is_recorded_on_the_live_history_and_audit_events`. Each of the two bulk actions has a distinct ID.<br>• **Live History:** each Agent's `bulk_publish` and `bulk_revert` entries carry the ID, with from/to and actor.<br>• **Audit Events:** `agent.bulk_published` and `agent.bulk_reverted` carry before/after with `bulk_operation_id`. The `project.agents_bulk_published` / `…_reverted` summaries carry the ID and counts (2 succeeded, 1 skipped).<br>**E2E:** Agent A's Live History reads `bulk_revert, bulk_publish, bulk_revert, bulk_publish, publish` with IDs on the bulk entries, and the Project summary events carry the same ID. |
| 8 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | The seams are listed above. The coverage gates are in the results below. No coverage exclusions were added. |
| 9 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md` adds **Bulk publish** (with the rollout dialog), **Bulk revert**, **Bulk operation** (with the bulk operation ID) and **Behind**. No ADR decision changed: ADR-0003 already decides that bulk publish uses the Live config, and this ticket follows it. |

## Results

All runs are local, one suite at a time (GitHub Actions is down; the user authorised merging on local results). The first full run was at `c5376a5`. `origin/candidate` then moved to `102056d` (05-04, Diffs and Draft management, #51), so it was merged into the branch as `ba648fe`. The conflicts were all additive: both tickets added routes, OpenAPI operation IDs, tenant-isolation rows and Studio props, and both sides were kept (`PublishInstructionsForm` takes 05-04's stale-Draft handling and this ticket's `onPublished`; `InstructionsTab` keeps 05-04's reload-on-conflict and this ticket's rollout and revert dialogs). The API client was regenerated. **Every check below was re-run at `ba648fe`** with no uncommitted code changes. Each log's first line names the command and the commit.

| Check | Command | Result | Log |
|---|---|---|---|
| Install | `make install` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc) | exit 0 | [lint.log](lint.log) |
| API client drift | `make check-client` | "API client is up to date." | [client-drift.log](client-drift.log) |
| Backend tests + coverage gate | `make test-backend` against fresh `rag0505-svc` Postgres/pgvector, Redis and RustFS containers (ports 48532/48579/48591); OpenTelemetry span lines filtered out | **1870 passed**, 7 deselected (live); coverage **100.00%** lines and branches | [backend-tests.log](backend-tests.log) |
| Frontend tests + coverage gate | `make test-frontend` | **46 files, 584 tests passed**; 100% statements, branches, functions and lines | [frontend-tests.log](frontend-tests.log) |
| Images | `build.sh` (sandbox `make images`) | both images built (`rag-agent-studio/api:0505`, `rag-agent-studio/studio:0505`), exit 0; removed afterwards | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` (project `rag0505-e2e`, host ports 49510–49625) | **68 passed** (3.0 min), including `bulk-rollout.spec.ts` with its axe scans; exit 0 | [e2e.log](e2e.log) |
| Security | gitleaks (`origin/candidate..HEAD`), `make audit` (pip-audit, pnpm audit) | no leaks, no known vulnerabilities | [security.log](security.log) |
| Infra | terraform checks | not run: this ticket changes no infra | n/a |

## Gaps and best guesses

- **Out of this ticket's scope:**
  - A Visitor-facing route arrives with 06-01, so "Agent A serves v2/v1" is checked through the API (the Live Version and its pinned Instructions), and in the API seam through the serving module with the echo model.
  - 05-04 (Diffs and Draft management), merged while this ticket was in review, added `has_unpublished_changes` to the Agent. The rollout summary's `has_draft_changes` is computed separately (Draft config ≠ Live Version config). The two agree today; a follow-up could make the rollout reuse 05-04's flag.
- **Best guesses, recorded instead of asking:**
  - **Agents already on the chosen Instructions Version are skipped**, rather than given an identical new Version.
  - **A bulk action names at most 200 Agents.** The spec sets no limit.
  - **"Not found" for IDs outside the Project** is a per-Agent failure (the rest still run), not a 404 for the whole request, so one stale ID doesn't block a rollout. Another Organisation's Agent is indistinguishable from no Agent.
  - **The default note** is "Bulk published with Instructions vN"; the API accepts a custom one, and the Studio uses the default.
  - **A summary Audit Event on the Project** is recorded per bulk action, in addition to the per-Agent events, so one entry describes the whole operation.
  - **Bulk publish doesn't recheck credentials.** A Live Version's credentials can't be deleted (05-02), so the Live config always runs.
  - **The rollout dialog opens after every Instructions publish**, even with no Agents (it then says so), and the "N Agents behind" summary counts only live Agents.
  - **The Instructions revert response** gained `reverted_from` and `bulk_revert_candidates` rather than a separate endpoint, as the spec's "Instructions revert returns the bulk-revert candidates" suggests.
- **Sandbox limits** (as in earlier tickets):
  - Images are built with `WITH_PDF=false BUNDLE_MODELS=false` (`build.sh` adds only the egress proxy CA), and the e2e stack runs `EMBEDDER=fake`, because Hugging Face is blocked here.
  - The live suite and the Trivy image scan were not run.
  - Infra checks were not run; this ticket changes no infra.
