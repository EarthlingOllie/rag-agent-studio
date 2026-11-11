# Evidence: ticket 05-02, Publish Agent to Live Version

Branch `ticket/05-02-publish-agent-live-version`, from `origin/candidate` at `22b8cf6` (05-01, Project Instructions Versions, merged; 04-07 was already there). The claim commit `6aa91bf`, the first on the branch, set Status `in-progress`. The feature is `98028e1`. `origin/candidate` then moved to `01dc516` (03-02's live Docling models and screenshots: backend Dockerfile, `pyproject.toml` and `uv.lock`, test fixtures and docs, no migration), merged cleanly in `b1ed268`. This ticket's migration is `0026_agent_versions`, revising `0025_instructions_versions`, so candidate keeps one Alembic head.

**Status: done.** Every criterion is met and evidenced below. The gaps at the end are scope this ticket leaves to later tickets on purpose, plus what this sandbox can't run.

## What was built

- **Data** (`backend/app/agents/models.py`, migration `backend/migrations/versions/20261106_0026_agent_versions.py`):
  - `agent_versions`: number (1, 2, 3… per Agent, unique per Agent), the Draft's AgentConfig as JSON, the pinned `instructions_version_id` (null only when the Project had never published its Instructions), note, author, created time.
  - `agents.live_version_id`: the **Live Version** pointer; null means the Agent is **not live**.
  - `agent_live_history`: from-Version (null for the first publish), to-Version, action (`publish` now; `revert`, `bulk_publish`, `bulk_revert` are for 05-03 and 05-05), actor, time, `bulk_operation_id`, and an identity `seq` that orders entries as written.
  - A trigger refuses every `UPDATE` on `agent_versions` and `agent_live_history`. Rows still go with their Agent (permanent deletion) and Organisation (`erase_organisation`), by cascade, which deletes and never updates.
  - `messages.agent_version_id`: the Agent Version that answered. `config_source` is `draft` (Playground) or `version`.
- **Service** (`backend/app/agents/versions.py`, rules in its docstring): **publish** locks the Agent row (`SELECT … FOR UPDATE`), allocates the next number inside the lock, snapshots the Draft, pins the chosen Instructions Version or else the Project's Current Version, moves Live, writes the Live History entry and records the `agent.published` Audit Event, all in one transaction. Archived Agents and Projects are refused. Also: the Version list, one Version, the Live History, and `served`, which resolves the Live Version's config and pinned Instructions text.
- **Serving contract** (`backend/app/agents/serving.py`): what spec 06's widget will call. It finds an active Agent of an active Project by public ID, refuses an Agent that is not live, starts a Visitor Conversation, and saves a question prepared with the Live Version's config and pinned Instructions. `app.playground.service.answer` (shared with the Playground) then stores the answer with `config_source = version` and the `agent_version_id`. The Playground still runs the Draft with the Instructions Draft, and its answers keep the `draft` marker and no Version.
- **Credential references** (`backend/app/agents/validation.py`): a credential the Live Version names stays referenced, as "<Agent> Live Version (model)", after the Draft stops naming it, so Visitors' configuration can't lose its credential.
- **API** (`backend/app/agents/versions_api.py`), for Editors and Owners, scoped by Organisation through the one policy dependency:
  - `POST …/agents/{id}/versions` (`publishAgent`), body `{note, instructions_version_id?}`: returns 201 with the Version. 409 for an archived Agent or Project; 422 for a missing or over-long note, or an Instructions Version that isn't the Project's.
  - `GET …/agents/{id}/versions` (`listAgentVersions`): `{live_version_id, versions}`, newest first.
  - `GET …/agents/{id}/versions/{version_id}` (`getAgentVersion`).
  - `GET …/agents/{id}/live-history` (`listAgentLiveHistory`), newest first.
  - `AgentOut` gains `live_version: {id, number} | null`. Playground `MessageOut` and `TraceOut` gain `agent_version_id`.
  - No route changes or deletes a Version or a Live History entry.
- **Studio** (`frontend/apps/studio/src/projects/AgentPublish.tsx`):
  - The Agent page shows a **Not live** badge, with "Visitors can't use it until you publish it.", or **Live vN**. The Agents list shows the same badge for each Agent.
  - The **Publish** form takes a required note (up to 500 characters) and a **Project Instructions** picker: "Current Version (vN)" by default, any Instructions Version, or "None (no Instructions published)". It publishes the saved Draft and then shows "Published vN with Instructions vM. It is now Live." Refusals show the API's reason. An archived Agent has no Publish form.
- The **generated API client** was regenerated (`make gen-client`).

## Test seams

These follow the [shared test seams](../../../specs/README.md#shared-test-seams). They were not confirmed with a human; they are the ones the spec's Testing Decisions name.

- **API seam:** `backend/tests/integration/test_agent_versions.py` (22 tests, 31 cases) drives the app in process against real Postgres and Redis. It asserts on HTTP responses and what reads back through the API, including the Audit API. The exceptions are deliberate:
  - The defence-in-depth direct `UPDATE`.
  - The serving tests. No API serves Visitors until 06-01, so they call the serving module (the runtime contract) directly with the echoing `FunctionModel`, and read the saved answer's attribution with one `SELECT`.
  - The cascade test, which counts the remaining Versions.
- `test_tenant_isolation.py` adds the four routes: other Organisations get 404, unauthenticated requests get 401, Editors are allowed. `test_openapi.py` lists the four operations. `test_migrations.py` runs the up/down/up round trip through `0026`, and `alembic check` confirms the models match.
- **Network seam:** `frontend/apps/studio/src/projects/AgentPublish.test.tsx` (11 tests), with the `fakeAgentsApi` MSW fake extended with a stateful publish.
- **End-to-end seam:** `frontend/e2e/tests/agent-publish.spec.ts`, Playwright against the docker compose stack, with axe.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Publishing creates an immutable Version (config snapshot plus pinned Instructions Version, Current by default, optionally chosen) and sets the Live Version under a lock | **Publish and Live:**<br>• `test_publishing_makes_v1_the_live_version`: number, note, author, config and `live_version`.<br>• `test_each_publish_adds_the_next_version_and_makes_it_live`<br>**Snapshot:** `test_the_version_is_a_snapshot_of_the_draft_that_later_edits_leave_alone`<br>**Pinning:**<br>• `test_a_version_pins_the_current_instructions_version_by_default`: the Current Version, not the Instructions Draft.<br>• `test_an_editor_can_pin_an_older_instructions_version`<br>• `test_only_an_instructions_version_of_the_agents_project_can_be_pinned`: another Project's or an unknown one gives 422 and no Version.<br>• `test_served_messages_record_the_live_version_and_run_its_pinned_instructions`: the echo model receives the pinned Instructions and the Live prompt, not a later Draft or newer Instructions.<br>• `test_a_version_without_instructions_runs_with_none`<br>**Lock:** `SELECT … FOR UPDATE` on the Agent row in `versions.publish`; see criterion 6.<br>**Refusals:** `test_publishing_takes_a_note` (5 cases), `test_an_archived_agent_or_project_cannot_be_published`, `test_versions_are_not_found_outside_their_agent_and_organisation`.<br>**Studio:** `AgentPublish.test.tsx`:<br>• publishing pins the Current Version (exact request body)<br>• pinning an older Version<br>• no Instructions published<br>• note required and limited; refused publishes (409, 422, 500)<br>• picker load failure; archived Agent<br>**E2E:** `agent-publish.spec.ts` publishes with the Current Instructions v1 and reads it back through the API. |
| 2 | The database refuses updates to Versions | Trigger `agent_versions_immutable` in migration `0026`.<br>• `test_the_database_refuses_to_change_a_version_or_its_live_history`: three direct `UPDATE`s (note, config, a Live History action) raise "immutable", and nothing changes.<br>• `test_versions_cannot_be_changed_through_the_api`: PUT, PATCH and DELETE on the Version collection, a Version and the Live History, and POST on a Version, all give 405.<br>• `test_deleting_the_agent_or_erasing_the_organisation_removes_its_versions`: permanent Agent deletion (03-11's and 04-09's cascade) and `erase_organisation` still succeed with Versions, Live History, pinned Instructions and attributed Messages, because cascades delete rows and never update them. |
| 3 | Live History entries are written | `test_each_publish_writes_a_live_history_entry`: from-Version, to-Version, `publish`, actor, time and no bulk operation, newest first. `test_concurrent_publishes_get_consecutive_unique_numbers` checks that each entry moves Live on from the one before. `test_an_agent_without_a_version_is_not_live` checks the history starts empty. The E2E reads `[[null, 1, "publish"]]` from the API. |
| 4 | Messages record their Agent Version, or a Draft marker in the Playground | • `test_playground_messages_record_the_draft_even_once_the_agent_is_live`: `config_source` `draft` and `agent_version_id` null, in the Conversation and the Trace.<br>• `test_served_messages_record_the_live_version_and_run_its_pinned_instructions`: `config_source` `version`, the Live Version's ID, a non-Playground Conversation.<br>• `test_an_agent_that_is_not_live_serves_nothing`, `test_a_served_question_needs_a_visitor_conversation_of_that_agent`<br>• `test_playground.py::test_an_editor_asks_the_draft_and_the_answer_streams_back` still asserts `config_source == "draft"`. |
| 5 | An Agent without a Version is shown as not live | API: `test_an_agent_without_a_version_is_not_live` (`live_version` null on create, get and list; no Versions; no Live History).<br>Studio:<br>• "an Agent that has never been published is shown as not live"<br>• "the Agents list shows which Agents are live and which aren't"<br>• "publishing … makes the Draft the Live Version": Not live becomes Live v1<br>E2E: Not live before publishing, Live v1 after, on the Agent page and in the Agents list, with axe scans. |
| 6 | Concurrent publishes produce consecutive, unique numbers | `test_concurrent_publishes_get_consecutive_unique_numbers`: 8 parallel requests from two Members against real Postgres. All give 201, with numbers exactly 1–8. The highest is Live, and the Live History chains 8→7→…→1→none. |
| 7 | Publishing is recorded as an Audit Event | `test_publishing_is_recorded_as_an_audit_event`: `agent.published`, with exact actor and target, before `{live_version}` and after `{live_version: {version_id, number, note, instructions_version}}`, for two publishes. Refused publishes record nothing (in the pinning and archived tests). The E2E reads `agent.published` = `[[1, "First release"]]` from the Audit API. |
| 8 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | The seams are listed above. The coverage gates are in the results below: backend `fail_under = 100` with branches, and frontend Vitest at 100% for every metric. No coverage exclusions were added. |
| 9 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md`:<br>• **Version** gains Agent Version, consecutive numbering and the pinning rule (Current by default, chosen, or none)<br>• **Live Version** gains "Not live"<br>• **Live History** gains its entry fields<br>• **Message** gains Message attribution (Agent Version or Draft marker)<br>No ADR decision changed: ADR-0003 (immutable Versions, a movable Live pointer, Agent Versions pin Instructions) is followed as written. |

## Results

All runs are local, one suite at a time (GitHub Actions is down; the user authorised merging on local results). Every check ran at `b1ed268`, the merge of `origin/candidate` at `01dc516`, with no uncommitted code changes (only this folder and the ticket file were being written). Each log's first line names the commit it ran at.
- The backend ran against fresh `rag0502-*` containers on host ports 48532 (Postgres), 48579 (Redis) and 48591 (RustFS), which no other ticket uses.
- The e2e stack ran as compose project `rag0502-e2e`, on host ports 46310–46825.
- Before the merge, at `98028e1`, the backend (1721 passed, 100%), frontend (517 passed, 100%) and e2e (64 passed) runs were also green.

| Check | Command | Result | Log |
|---|---|---|---|
| Install | `make install` (uv sync --frozen, pnpm install --frozen-lockfile) | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc) | exit 0 | [lint.log](lint.log) |
| API client drift | `make check-client` | "API client is up to date." | [client-drift.log](client-drift.log) |
| Backend tests + coverage gate | `make test-backend` against fresh `rag0502-*` Postgres/pgvector, Redis and RustFS containers (ports 48532/48579/48591); the OpenTelemetry span lines are filtered out of the log | **1721 passed**, 7 deselected (live); coverage **100.00%** lines and branches | [backend-tests.log](backend-tests.log) |
| Frontend tests + coverage gate | `make test-frontend` | **41 files, 517 tests passed**; 100% statements, branches, functions and lines | [frontend-tests.log](frontend-tests.log) |
| Images | `build.sh` (sandbox `make images`) | both images built (`rag-agent-studio/api:0502`, `rag-agent-studio/studio:0502`), exit 0 | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` (project `rag0502-e2e`) | **64 passed** on the first attempt (3.2 min), including `agent-publish.spec.ts` with its axe scans | [e2e.log](e2e.log) |
| Security | gitleaks (`origin/candidate..HEAD`), `make audit` (pip-audit, pnpm audit) | no leaks, no known vulnerabilities | [security.log](security.log) |
| Infra | terraform checks | not run: this ticket changes no infra | n/a |

## Gaps and best guesses

- **Out of this ticket's scope, left to the tickets named:**
  - Revert, the Live History timeline in the Studio, and revert audit events (05-03). The `revert` action value and the history API are ready for it.
  - Diffs, including the publish dialog's Draft-to-Live diff preview, the unpublished-changes badge, discard and start-from-Version, and the stale-Draft 409 (05-04).
  - Bulk publish and revert, which write `bulk_operation_id` (05-05).
  - The Playground Instructions picker, and Playground Messages recording the Instructions Version (05-06).
  - The Studio's Version list panel (story 8) belongs with 05-03 and 05-04's history and diff views. The list and Version API is here.
  - A Visitor-facing route (06-01). Serving is exposed as the `app.agents.serving` module and tested there.
- **Best guesses, recorded instead of asking:**
  - **The pin can be empty.** A Project that has never published its Instructions gives Versions no pinned Instructions Version, and they run with no Project Instructions, not the unpublished Draft. Refusing to publish until the Instructions are published would block Projects that use no Instructions.
  - **Identical publishes are allowed.** Unlike 05-01's Instructions, publishing a Draft equal to the Live Version still makes a new Version. Story 34 accepts "two distinct Versions", and the criterion asks for consecutive, unique numbers under concurrency. A new Version may also exist only to pin different Instructions.
  - **The note is required** (1–500 characters, trimmed), as for Instructions in 05-01.
  - **Publish uses the saved Draft.** The Studio autosaves the Draft (04-07), and the form says it publishes the saved Draft.
  - **Credentials are protected for the Live Version only.** Older Versions don't hold their credentials, so a credential an older Version names can be deleted. 05-03 should check that a revert target's credentials still exist.
  - **Live History is also immutable.** It is append-only by the spec, so the same trigger refuses UPDATEs to it.
- **Sandbox limits** (as in earlier tickets):
  - Images are built with `WITH_PDF=false BUNDLE_MODELS=false` (`build.sh` adds only the egress proxy CA), and the e2e stack runs `EMBEDDER=fake`, because Hugging Face is blocked here.
  - The live suite and the Trivy image scan were not run.
  - Infra checks were not run; this ticket changes no infra.
