# Evidence: ticket 05-04, Diffs and Draft management

Branch `ticket/05-04-diffs-draft-management`, from `origin/candidate` at `0e5ef28` (05-02, Publish Agent to Live Version, merged). The claim commit `d3e0d7c`, the first on the branch, set Status `in-progress`. The feature is `3957302`, with follow-ups `7f42f67` (tenant isolation listing) and `5877c4d` (Instructions revision after a publish; e2e waits). `origin/candidate` then moved to `be524a3` (05-06, Playground Instructions picker), merged in `1401464`. 05-06's migration took `0027`, so this ticket's migration is `0028_draft_revisions`, revising `0027_playground_instructions`, and candidate keeps one Alembic head.

**Status: done.** Every criterion is met and evidenced below. The gaps at the end are scope left to later tickets, best guesses, and what this sandbox can't run.

## What was built

- **Diff module** (`backend/app/versioning/diff.py`, rules in its docstring), used by Agents and Project Instructions:
  - `diff_configs`: a structural diff of two AgentConfigs. Every differing setting is reported by its dotted path, in AgentConfig order. Groups are walked field by field. A Model choice set or cleared is one change of the whole value. A list (Tags, starter questions) reports the items added and removed; a reorder has neither. Markdown fields (the system prompt) also get a line diff.
  - `diff_text`: a line diff (`equal`, `delete`, `insert`).
- **Agent diff** (`versions.diff`, `GET …/agents/{id}/diff?from=…&to=…`, `diffAgent`). Each side is `draft`, `live` or a Version ID. Between two Versions, the response also carries the change of pinned Instructions Version and a line diff of their text. The Draft pins no Instructions until it is published, so a Draft side shows none. `live` on an Agent that is not live gives 409. A Version of another Agent or Organisation gives 404, and an unknown side gives 422.
- **Instructions diff** (`instructions.diff`, `GET …/projects/{id}/instructions/diff?from=…&to=…`, `diffProjectInstructions`). Each side is `draft`, `current` or an Instructions Version ID, compared line by line. 05-01 left Instructions diffs to this ticket.
- **Unpublished changes.** `AgentOut.has_unpublished_changes` is true when the Draft differs from the Live Version's AgentConfig, and false while the Agent is not live. The Agent page and the Agents list show an **Unpublished changes** badge beside Live vN.
- **Draft revisions** (migration `0028_draft_revisions`): `agent_drafts.revision` and `projects.instructions_revision`.
  - Every Agent Draft change moves the revision on. `AgentOut.draft_revision` exposes it.
  - The Instructions revision moves on when the text changes. `GET`/`PUT …/instructions` return `{markdown, revision}`.
  - `PUT …/agents/{id}/draft` and `PUT …/instructions` take an optional `base_revision` query parameter. When the Draft has moved on from it, the save returns **409** `{detail, latest}`, with the latest Draft, and changes nothing. The stale check comes before the settings check. Without `base_revision` the Draft is replaced, as before, so the seed and API scripts keep working. The Studio always sends it.
- **Discard the Draft** (`POST …/agents/{id}/draft/discard`, `discardAgentDraft`): the Live Version's AgentConfig goes back in the Draft. 409 while the Agent is not live. Audited as `agent.draft_discarded`.
- **Start a Draft from a Version** (`POST …/agents/{id}/draft/from-version`, `startAgentDraftFromVersion`, body `{version_id}`): that Version's AgentConfig replaces the Draft, and nothing is published. The settings are checked like a save, so a Version naming a credential deleted since gives 422. Audited as `agent.draft_started_from_version`.
- Both Draft actions honour `base_revision` (409 with the latest Draft), refuse archived Agents and Projects (409), move the revision on, and are Editor or Owner, in the tenant isolation test.
- **Studio:**
  - The **Publish** form gains "Changes from the Live Version (vN)": the Draft-to-Live diff (`AgentDiff.tsx`). It shows each setting with before → after, Tags by name, items added and removed, a −/+ line diff for the system prompt, and "No differences" when there are none. A first publish says the whole Draft goes live. The diff is fetched again whenever the Draft's revision changes.
  - **Discard Draft**, with confirmation, while there are Unpublished changes.
  - A **Versions** panel (`AgentVersions.tsx`) lists each Version newest first: number, Live marker, note, author, time and pinned Instructions. Each Version has **Start Draft from vN**, with confirmation; an archived Agent has none. **Compare** takes any two of the Draft and the Versions. It defaults to the Live Version against the Draft and shows the pinned Instructions change.
  - The Draft editor sends the revision its edits were made on. On a 409 it shows "Someone else saved this Draft while you were editing" with **Load their changes**, which restarts the editor from their Draft, or **Save mine over theirs**, which saves again on their revision. The status reads "Not saved: someone else changed this Draft."
  - The Instructions tab handles the Instructions Draft the same way, for both Save and Publish (publish saves first). It gains a **Compare** section for any two Instructions Versions or the saved Draft.
- The **generated API client** was regenerated (`make gen-client`).

## Test seams

These follow the [shared test seams](../../../specs/README.md#shared-test-seams). They were not confirmed with a human; they are the ones the spec's Testing Decisions name ("Diff: tested through its interface…", the API seam scenarios, "the 409 conflict prompt" at the network seam, and an end-to-end run).

- **Diff interface:** `backend/tests/unit/test_config_diff.py` (10 tests). AgentConfig pairs cover nested groups, Model choices, lists (Tags, starter questions), reordering, markdown and plain text.
- **API seam** (in process against real Postgres and Redis, asserting on HTTP responses and the Audit API):
  - `backend/tests/integration/test_agent_diffs.py` (8 tests)
  - `test_agent_draft_management.py` (14 tests, 15 cases)
  - `test_project_instructions_diffs.py` (4 tests)
  - `test_project_instructions_draft.py` (3 tests)
  - `test_tenant_isolation.py` adds the four new routes (404 for other Organisations, 401 unauthenticated, Editors allowed).
  - `test_openapi.py` lists the four operations.
  - `test_migrations.py` round-trips through `0028`.
- **Network seam:** `frontend/apps/studio/src/projects/AgentDrafts.test.tsx` (22 tests) and `InstructionsDrafts.test.tsx` (10 tests). They run against MSW fakes made stateful for revisions, Versions and discards (`src/test/agents.ts`, `src/test/projects.ts`), with a `colleagueSaves` helper that simulates another Editor.
- **End-to-end seam:** `frontend/e2e/tests/agent-drafts.spec.ts`, Playwright against the docker compose stack, with axe scans. It covers the badge, the publish form's diff, discard, start from v1, compare v1 → v2, and a colleague's save loaded through the conflict prompt.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | A structural AgentConfig diff with text diffs for markdown covers Version-to-Version and Draft-to-Live | **Diff interface:** all of `test_config_diff.py`.<br>**API:**<br>• `test_the_draft_compared_with_the_live_version`: exact JSON for a changed markdown prompt with its line diff, a scalar and a list.<br>• `test_two_versions_compared_with_their_pinned_instructions`: both directions, with the Instructions line diff.<br>• `test_versions_pinning_the_same_instructions_show_no_instructions_change`<br>• `test_pinning_instructions_for_the_first_time_shows_their_whole_text`<br>• `test_an_unchanged_draft_has_no_changes`<br>• refusals: `test_comparing_with_the_live_version_of_an_agent_that_is_not_live_is_refused`, `test_a_version_of_another_agent_or_organisation_is_not_found`, `test_a_side_must_be_draft_live_or_a_version_id`<br>**Instructions** (story 30, left here by 05-01): `test_project_instructions_diffs.py`.<br>**Studio:**<br>• "an Editor compares any two Versions, including their pinned Instructions"<br>• "a comparison of Versions whose only change is the pinned Instructions shows just that"<br>• "a comparison that can't be loaded says so"<br>• "an Agent that is not live compares the Draft with itself by default"<br>• the Instructions compare tests in `InstructionsDrafts.test.tsx`<br>**E2E:** compare v1 → v2 shows "Added: + Be brief." |
| 2 | An unpublished-changes badge is shown | **API:** `test_the_agent_says_when_its_draft_has_unpublished_changes`: false when not live and right after publishing, true after an edit (get and list), false again when edited back to the Live config and after the next publish.<br>**Studio:**<br>• "a live Agent whose Draft differs from the Live Version is badged"<br>• "the badge appears once a change to a live Agent's Draft is saved, and goes once it is published"<br>**E2E:** the badge after a Draft edit, gone after discard, back after starting from v1. |
| 3 | Editors can discard the Draft, or start a Draft from any Version | **API:**<br>• `test_discarding_the_draft_restores_the_live_configuration`: an Editor; the Draft equals the Live config; the revision moves on; `agent.draft_discarded` audited with exact before and after.<br>• `test_an_agent_that_is_not_live_has_no_draft_to_discard`<br>• `test_starting_the_draft_from_an_earlier_version`: v2 stays Live; Unpublished changes; `agent.draft_started_from_version` audited.<br>• `test_starting_from_a_version_of_another_agent_is_not_found`<br>• `test_a_version_whose_credential_is_gone_cant_start_the_draft` (422, Draft unchanged)<br>• `test_an_archived_agents_draft_cant_be_discarded_or_started_from_a_version` (Agent and Project)<br>• `test_draft_actions_on_an_unknown_agent_are_not_found`<br>**Studio:**<br>• "an Editor discards the Draft back to the Live Version after confirming", including cancel<br>• "an Editor starts the Draft from an earlier Version after confirming", including cancel<br>• "a Version whose credential is gone can't start the Draft"<br>• "other refusals of a Draft change show the API's reason"<br>• "an archived Agent's Versions can be read but start no Draft, and it offers no discard"<br>• the Version list tests<br>**E2E:** discard and start from v1 through the UI, both audited (read from the Audit API). |
| 4 | Saving a stale Draft returns 409 with the latest Draft, and the UI prompts to resolve the conflict | **API, Agents:**<br>• `test_saving_a_stale_draft_is_refused_with_the_latest_draft`: two Members; 409 with `latest` equal to the colleague's saved Agent; unchanged; saving over it on the latest revision works.<br>• `test_each_save_moves_the_draft_to_its_next_revision`<br>• `test_a_stale_save_is_refused_before_its_settings_are_checked`<br>• `test_a_save_without_a_base_revision_replaces_the_draft`<br>• `test_discarding_a_draft_someone_has_since_changed_is_refused`<br>• `test_starting_from_a_version_someone_has_since_changed_is_refused`<br>**API, Instructions:** `test_project_instructions_draft.py`.<br>**Studio:**<br>• "a save refused because someone else saved first prompts to load their Draft": the alert, the status, then Load their changes restarts the editor from their Draft.<br>• "an Editor can save their Draft over a colleague's on purpose"<br>• "the Draft can't be discarded once someone else has changed it, and their Draft is shown"<br>• the Instructions equivalents, including publish and publishing twice in a row<br>**E2E:** a colleague's save through the API, then a UI edit, shows the prompt (axe-scanned); Load their changes shows their prompt and the API agrees. |
| 5 | The publish dialog shows the Draft-to-Live diff | **Studio:**<br>• "the publish dialog shows what the Draft changes from the Live Version": the request is `from=live&to=draft`; every kind of change renders (markdown lines, Model choice, number, Tags by name or ID, boolean, list added and removed, empty text, cleared text, reorder).<br>• "the publish dialog says when the Draft is the same as the Live Version"<br>• "the first publish says the whole Draft goes live, without asking for a diff"<br>• "the publish dialog says when the diff can't be loaded"<br>**E2E:** the Publish form's "Changes to publish" shows the system prompt's −/+ lines against Live v2, then "No differences" after discarding (axe-scanned). |
| 6 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | The seams are listed above. The coverage gates are in the results below: backend `fail_under = 100` with branches, and frontend Vitest at 100% for every metric. No coverage exclusions were added. |
| 7 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md` adds **Draft revision** (stale Draft, a concurrency token, not a Version), **Unpublished changes**, **Discard the Draft**, **Start a Draft from a Version** and **Diff**. No ADR decision changed: ADR-0003 (immutable Versions, a movable Live pointer, Drafts never shipped unreviewed) is followed. Discarding and starting from a Version change only the Draft and publish nothing. |

## Results

All runs are local, one suite at a time (GitHub Actions is down; the user authorised merging on local results). Every check ran at `1401464` (`1401464`, the merge of candidate `be524a3`, before only this README and the ticket file were written), with no uncommitted code changes. Each log's first line names the commit it ran at.
- The backend ran against this ticket's own `rag0504-svc-*` containers (Postgres :48732, Redis :48779, RustFS :48791), with the `studio_test` database recreated first.
- The e2e stack ran as compose project `rag0504-e2e`, on host ports 45310–45825.

| Check | Command | Result | Log |
|---|---|---|---|
| Install | `make install` (uv sync --frozen, pnpm install --frozen-lockfile) | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc) | exit 0 | [lint.log](lint.log) |
| API client drift | `make check-client` | "API client is up to date." | [client-drift.log](client-drift.log) |
| Backend tests + coverage gate | `make test-backend` against the `rag0504-svc-*` Postgres/pgvector, Redis and RustFS containers; the OpenTelemetry span lines are filtered out of the log | **1801 passed**, 7 deselected (live); coverage **100.00%** lines and branches | [backend-tests.log](backend-tests.log) |
| Frontend tests + coverage gate | `make test-frontend` | **44 files, 556 tests passed**; 100% statements, branches, functions and lines | [frontend-tests.log](frontend-tests.log) |
| Images | `build.sh` (sandbox `make images`) | both images built (`rag-agent-studio/api:0504`, `rag-agent-studio/studio:0504`), exit 0 | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` (project `rag0504-e2e`) | **66 passed** on the first attempt (3.7 min), including `agent-drafts.spec.ts` with its axe scans | [e2e.log](e2e.log) |
| Security | gitleaks (`origin/candidate..HEAD`), `make audit` (pip-audit, pnpm audit) | no leaks, no known vulnerabilities | [security.log](security.log) |
| Infra | terraform checks | not run: this ticket changes no infra | n/a |

`compose.sandbox.yml` and `e2e.env` (sandbox-only, in this folder) moved to host ports 45xxx after another stack held 49810. They are committed with this README.

## Gaps and best guesses

- **Out of this ticket's scope, left to the tickets named:**
  - Revert and the Live History timeline (05-03).
  - Bulk publish and revert, and the bulk dialog's Unpublished-changes badges (05-05). `has_unpublished_changes` on `AgentOut` is ready for it.
- **Best guesses, recorded instead of asking:**
  - **The concurrency token is a revision number**, not `updated_at`, which the spec allows. Timestamps can collide under the test clock and between fast saves.
  - **It is passed as an optional `base_revision` query parameter.** An `If-Match` header would conventionally answer 412, but the spec asks for 409. Leaving it out keeps the old replace behaviour for the seed and scripts; the Studio always sends it.
  - **Project Instructions get the same 409.** The ticket's wording ("Saving a stale Draft") and the spec's Concurrency section cover any Draft edit, and 05-01 left "the 409 on a stale Draft save" to this ticket. The Instructions revision moves only when the text changes, so re-saving identical text never conflicts.
  - **Instructions diffs are here** (story 30), because 05-01 deferred them to 05-04.
  - **An Agent that is not live has no Unpublished changes.** It is already badged "Not live", and there is nothing to compare with.
  - **Discard and start-from-Version check the settings like a save**, and refuse a Version whose credential or Tag is gone (422), rather than putting an invalid Draft in place. Only the Live Version protects its credentials (05-02).
  - **A Draft-side diff shows no Instructions change.** The Draft pins nothing until it is published, and the publish form has its own Instructions picker.
  - **Discard and start-from-Version are audited.** Ordinary Draft saves still aren't, as before.
- **Sandbox limits** (as in earlier tickets):
  - Images are built with `WITH_PDF=false BUNDLE_MODELS=false` (`build.sh` adds only the egress proxy CA), and the e2e stack runs `EMBEDDER=fake`, because Hugging Face is blocked here.
  - The live suite and the Trivy image scan were not run.
  - Infra checks were not run; this ticket changes no infra.
- **Before the final run:** an earlier e2e run at `7f42f67` failed 7 tests. Four existing specs waited for a `PUT` URL ending in `/draft`, which the new `?base_revision=` query broke. The Instructions spec read `{markdown}` exactly, but the response now also has `revision`. And the Instructions form kept a stale revision after a publish. All three were fixed in `5877c4d`, with a Vitest test for publishing twice, and the next run, before the merge of 05-06, passed 65 of 65.
