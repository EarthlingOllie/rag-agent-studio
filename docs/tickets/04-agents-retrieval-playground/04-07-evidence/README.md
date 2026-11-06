# Evidence: ticket 04-07, Full AgentConfig editor

Branch `ticket/04-07-full-agentconfig-editor`, from `origin/candidate` at `c1e455f` (04-01, the only blocker, merged). `origin/candidate` at `a35cef1` (03-05 and 04-03) was merged in at `0944bfc`, at `9e5a8bb` (03-03) at `b315f12`, and at `55e017e` (03-09) at `61be96d`. Every check below was rerun on the merged tree. The claim commit `2ed4132`, the first on the branch, set Status `in-progress`.

**Status: done.** Every criterion is met and evidenced below. The gaps at the end are scope left to later tickets on purpose, plus best guesses recorded instead of asking.

## What was built

An Editor configures every part of an Agent's Draft in the Studio. Changes save themselves once typing pauses, and a setting the API refuses is marked with the reason.

- **AgentConfig** (`backend/app/agents/config.py`) now has all four groups. Every field has a default, so stored Drafts stay valid:
  - **Behaviour:** `system_prompt`, `model` (the Model override: `{credential_id, model}` or `null` for the Default Model), `temperature` (0–1, default 0.7), `max_output_tokens` (1–8192, default 1024), `remembered_turns` (0–20, default 5), `fallback_text`.
  - **Retrieval:** `top_k`, `hybrid_weight`, `min_score`, `tag_ids` (up to 50, de-duplicated), `reranker` (`{credential_id, model}` or `null`), `citations` (default on).
  - **Experience:** `display_name` (empty shows the Agent's name), `avatar_url` (https only), `greeting`, `starter_questions` (up to 6, each 1–200 characters, trimmed), `ui_text` (`send_button`, `rate_conversation`, `unavailable_message`; `null` keeps the built-in text), `rating_prompt_after` (0–50, default 3; 0 asks only at the end).
  - **Guardrails** (stored only, until spec 08): `input_mode` (`block`/`warn`/`log`, default `block`), `classifier` (`{credential_id, model}` or `null`), `fail_mode` (`open`/`closed`, default `closed`), `refusal_text`.
  - Unknown settings are refused (`extra="forbid"`).
- **Database validation on save** (`backend/app/agents/validation.py`, `check_draft`):
  - Each credential the Draft names must belong to the Organisation and offer the chosen model for its setting's capability, checked against the capability registry through the gateway's `check_offered`. The model override and classifier need chat; the reranker needs rerank.
  - Each Tag must be one of the Agent's Project's Tags. Deleting a Tag (`delete_tag` in `app/tags/service.py`) also takes it out of every Draft in the Project that was scoped to it, so a deleted Tag never leaves a Draft that can't be saved again.
  - Every problem is reported at once, in one 422 shaped like FastAPI's request validation errors (`{loc, msg, type}`), so the Studio places each message beside its field. Range and shape errors come from Pydantic in the same shape.
  - The named credentials are share-locked while the Draft is written, as the Default Model does. A concurrent credential delete therefore either finishes first (and the save is refused) or sees the new reference (and is refused).
- **Credential references** (`agent_references`, registered in `app/main.py` beside the Default Model's source). Each Draft setting that names a credential is a reference, labelled `"<Agent> (model)"`, `"(reranker)"` or `"(Guardrail classifier)"`. Deleting the credential is refused with 409 listing them. The query filters the Organisation's Drafts by the three JSON paths.
- **Runtime and Playground honour Behaviour:**
  - `run_turn` passes `temperature` and `max_tokens` as Pydantic AI `ModelSettings`, and keeps only the last `remembered_turns` turns.
  - The Playground answers with the Draft's Model override when set, otherwise the Default Model. An Agent with an override needs no Default Model. The saved Message records the provider and model that answered.
- **OpenAPI:** `PUT …/agents/{agent_id}/draft` takes `AgentConfig-Input`, and responses carry `AgentConfig-Output` with the nested group, `ModelChoice`, `InputMode` and `FailMode` schemas. The TypeScript client is regenerated (`make gen-client`).
- **Studio** (`frontend/apps/studio/src/projects/DraftEditor.tsx`, `draft.ts`) replaces 04-01's two-field form. It has one fieldset per group:
  - Model pickers (Model override, Reranker, LLM classifier) list only credentials with the right capability, then that credential's models for it (`GET …/credentials/{id}/models/{capability}`). "None" clears the setting.
  - Tag scoping uses the Project's Tags as checkboxes. Starter questions are entered one per line. Emptied UI text and avatar fields become `null`.
  - **Autosave:** a change saves 600 ms after typing pauses. The `Draft status` live region reads "All changes saved", "Unsaved changes", "Saving…", "Not saved: fix the settings marked below." or "Not saved: <reason>".
    - Saves run one at a time, in order (a promise queue). A newer change waits for the save in flight instead of racing it, and a queued save that a newer one has replaced is skipped. So an older save can never land after a newer one.
    - Only the latest change's response sets the status.
    - A save that fails for any reason, including a dropped connection, reads "Not saved: something went wrong. Your next change tries again."
    - A credential chosen without a model yet is an unsaved change: the status reads "Unsaved changes: choose a model." and the picker says "Choose a model to use this credential."
    - A change still waiting when the Editor leaves the page is saved at once.
    - An empty number is caught before sending ("Enter a number.").
    - Refused settings get `aria-invalid` and an `aria-describedby` message.

## Test seams

These follow the [shared test seams](../../../specs/README.md#shared-test-seams) and the spec's Testing Decisions. No human was available to confirm the seams, so the ones the spec names were used.

- **API seam** (in process, real Postgres with pgvector and Redis, fake credential verifier):
  - `backend/tests/integration/test_agent_config.py` (new) and `test_agents.py`.
  - `test_playground.py`, where the chat model is a Pydantic AI `FunctionModel` that reports the `model_settings` and remembered questions it received.
  - `test_openapi.py` and `test_no_secret_in_responses.py`.
- **Frontend network seam (MSW):** `frontend/apps/studio/src/projects/DraftEditor.test.tsx` (new) and `AgentPage.test.tsx`. The fake Agents API in `src/test/agents.ts` now also serves credentials, models per capability and Tags.
- **End-to-end** against the docker compose stack, with the fake gateway, so no real provider is called:
  - `frontend/e2e/tests/agent-config.spec.ts` (new).
  - `playground.spec.ts`, updated for autosave.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | All configuration groups (behaviour, retrieval, experience, guardrails) are editable; guardrail settings are stored only, until spec 08 | **Code:** `app/agents/config.py` (four groups), `DraftEditor.tsx` (four fieldsets).<br>**API tests** (`test_agent_config.py`):<br>• `test_a_new_agents_draft_has_every_group_at_its_defaults` checks against a hand-written literal (`FULL_DEFAULT_DRAFT` in `tests/agents.py`).<br>• `test_an_editor_sets_every_setting_and_reads_it_back_exactly`: an Editor sets every field away from its default and it round-trips.<br>• `test_settings_can_be_cleared_back_to_following_the_default_model`<br>• `test_starter_questions_and_ui_text_are_trimmed`<br>**Behaviour reaches the model** (`test_playground.py`):<br>• `test_the_draft_chooses_the_model_and_its_settings`: the override model is built, `{temperature: 0.1, max_tokens: 300}` reach it, and the Message records `anthropic`/`claude-haiku-4-5`.<br>• `test_a_model_override_needs_no_default_model`<br>• `test_only_the_remembered_turns_reach_the_model`: 2 keeps the last two, 0 none.<br>**Guardrails stored only:** they round-trip above, and no runtime code reads them. The UI says "enforced in a later release".<br>**Frontend** (`DraftEditor.test.tsx`):<br>• `every configuration group is shown with the Draft's settings`<br>• `an Editor sets every Behaviour, Experience and Guardrails setting`<br>• `an Editor sets the Retrieval settings and Tag scoping`<br>• `the model override, reranker and classifier offer only credentials with the right capability`<br>• `a saved model override is shown…`, `a Project without Tags says so`<br>**E2E:** `agent-config.spec.ts` sets the Model override, temperature, greeting and Guardrail mode in the browser. After a reload every value is still there, and the Playground answer comes from `openai:gpt-4.1-mini` (the override), not the Default Model. |
| 2 | Validation against the capability registry gives clear messages | **Code:** `check_draft` in `app/agents/validation.py` and `check_offered` in `app/gateway/gateway.py`; errors are mapped beside each field in `DraftEditor.tsx`.<br>**API tests:**<br>• `test_a_model_the_credential_doesnt_offer_is_refused_with_a_clear_message` (6 cases). Each asserts the exact body, e.g. `{"loc": ["body","behaviour","model","model"], "msg": "OpenAI doesn't offer claude-haiku-4-5 for chat.", "type": "model_unavailable"}` and "This credential can't be used for rerank." on `credential_id`.<br>• `test_a_credential_from_elsewhere_is_refused`: another Organisation's credential or an unknown ID gives "Choose a Provider Credential from this Organisation."<br>• `test_tags_must_belong_to_the_agents_project`: another Project's Tag and an unknown Tag each give "Choose Tags from this Project.", located by index.<br>• `test_deleting_a_tag_takes_it_out_of_every_draft_that_scoped_to_it`: after a scoped Tag is deleted, the Draft reads back without it and saving it again is 200, not a 422 at `retrieval.tag_ids`.<br>• `test_every_problem_is_reported_at_once`<br>• `test_out_of_range_settings_are_refused_with_where_and_why` (27 cases): each 422 is located at its field, has a message, and leaves the Draft unchanged.<br>**Frontend:** `settings the API refuses are marked with its reasons and not saved` (the message is the control's accessible description, with `aria-invalid`) and `an empty number is caught before saving`.<br>**E2E:** temperature 5 is refused (422), "Input should be less than or equal to 1" is shown beside the field, the axe scan is clean, and fixing it saves. |
| 3 | Drafts autosave, with an indicator | **Frontend** (`DraftEditor.test.tsx`):<br>• `a change autosaves after a pause, with an indicator`: "Unsaved changes", then "All changes saved"; typing "0.2" is one save.<br>• `the indicator shows a save in progress` ("Saving…")<br>• `a save that succeeds/fails after a newer change doesn't decide the status`<br>• `a failed save says so, and the next change tries again`<br>• `a save the network drops says so, and the next change tries again` (MSW `HttpResponse.error()`, so `fetch` rejects with a `TypeError`): the status reads "Not saved: something went wrong…", no field is marked, and the next change saves.<br>• `saves run one at a time, so an older save can't overwrite a newer one`: while the first PUT is held, the newer change is not sent and the status is not "All changes saved". A further change queued behind it replaces the waiting one, so after release the PUTs are "H" then "Hi!".<br>• `a credential chosen without a model is an unsaved change, not a saved one`: the status reads "Unsaved changes: choose a model." and nothing is sent until a model is chosen.<br>• `an archived Project's Draft can't be changed` ("Not saved: This Project is archived…")<br>• `a change still waiting to be saved is saved when the Editor leaves the page`<br>**E2E:** every change in `agent-config.spec.ts` waits for its `PUT …/draft` and then checks `Draft status` reads "All changes saved"; `playground.spec.ts` saves the system prompt the same way. |
| 4 | Credential references are registered for the model override, reranker and classifier | **Code:** `agent_references` in `app/agents/validation.py`, registered in `app/main.py`.<br>**API tests:**<br>• `test_credentials_an_agent_uses_cant_be_deleted`: deleting each of the three credentials gives 409 with references such as `{"kind":"agent","id":…,"name":"HR helper (Guardrail classifier)"}`, `"Benefits FAQ (model)"` and `"HR helper (reranker)"`. Clearing the Drafts releases them (204).<br>• `test_references_are_only_reported_in_their_own_organisation`<br>**E2E:** deleting the override's credential through the API returns 409 with `HR helper (model)`. |
| 5 | The AgentConfig JSON Schema is exposed through OpenAPI and covered by the client drift check | **Test:** `test_openapi.py::test_the_agentconfig_json_schema_types_the_draft_editor`. It checks the four required groups, `additionalProperties: false`, the temperature bounds, `ModelChoice` refs for the model override and reranker, `maxItems: 6` for starter questions, the `InputMode` enum, and that the request body has no required fields.<br>**Client:** `frontend/packages/api-client/openapi.json` and `schema.gen.ts` are regenerated. `DraftEditor.tsx` is typed by `Schemas["AgentConfig-Output"]`, so `tsc` fails if the schema and the form drift apart.<br>**Drift check:** `make check-client` reports "API client is up to date." ([client-drift.log](client-drift.log)). |
| 6 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | See the seams above and the results below. The round-2 fixes (deleted Tags leave Drafts, dropped-connection saves, one save at a time, a credential waiting for a model) are each covered by a test at the API or MSW seam, written failing first (rows 2 and 3).<br>• Backend gate: `fail_under = 100` with branch coverage, 100%.<br>• Frontend Vitest gate: 100% statements, branches, functions and lines. |
| 7 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md` (Agents and versioning) gains **Model override**, **Remembered turns**, **Starter question**, **UI text override** and **Autosave**. No ADR changed: AgentConfig still excludes Operational Settings and the Theme (ADR-0009), and model calls still go through the gateway. |

## Results

All runs are local and sequential, from the merged tree `61be96d` (origin/candidate `55e017e`, 03-09, merged in; the only conflict was `app/main.py`, where both credential-reference sources are now registered). GitHub Actions is down; the user authorised merging on local results.

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `make test-backend` against the `rag0407-pg` (pgvector), `rag0407-redis` and `rag0407-rustfs` containers | **1167 passed**, 1 failed, 6 deselected (live); coverage **100%** lines and branches (5785 statements, 560 branches). The one failure, `test_logging.py::test_the_api_server_writes_only_json_lines`, was `Connection refused` on the API subprocess's free port while six suites shared the machine (load average above 12). It is untouched by this ticket and passed 3 of 3 reruns of `test_logging.py`. | [backend-tests.log](backend-tests.log), [backend-logging-rerun.log](backend-logging-rerun.log) |
| Frontend tests + coverage gate | `make test-frontend` | **34 files, 361 tests passed**; 100% statements, branches, functions and lines | [frontend-tests.log](frontend-tests.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc) | exit 0 | [lint.log](lint.log) |
| API client drift | `make check-client` | "API client is up to date." | [client-drift.log](client-drift.log) |
| Security | `make audit` (pip-audit, pnpm audit); gitleaks over this branch's commits not on candidate | no known vulnerabilities, no leaks | [security.log](security.log) |
| Images | `build.sh` (sandbox `make images`) | both built | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` (project `rag0407`), on images built from the merged tree | First run: 47 passed, 1 failed (`tags.spec.ts`, a Tag not visible within 5 s, load average above 20). Two full reruns on the same stack: **48 passed** each, including `agent-config.spec.ts`, `playground.spec.ts` and 03-09's Embedding Model spec. | [e2e.log](e2e.log), [e2e-rerun.log](e2e-rerun.log) |
| Infra | not run | this branch changes nothing under `infra/` | |

## Gaps and best guesses

- **Left to the tickets that enforce these settings.** 04-07 makes them editable and stored:
  - Tag scoping in retrieval (04-04). The editor stores `tag_ids` and validates them against the Project.
  - Calling the Reranker (04-05). The editor stores it and validates its rerank capability.
  - Citations shown to Visitors (04-06/06-01).
  - Experience fields in the widget (06), and rating prompt timing (07).
  - Guardrail settings (08), stored only, as the criterion says.
  - Hybrid weighting, minimum score and fallback text are enforced by 04-03, which is built in parallel. Their fields here are copied verbatim from that branch, so the two merge cleanly.
- **Merged with 04-03.** 04-03 replies with the fallback text when retrieval returns no Chunks; `run_turn` now does that and also keeps the last `remembered_turns` turns with this ticket's model settings. 04-03's `DraftForm` and its two Studio tests are replaced by `DraftEditor` and its tests, which cover the same fields.
- **Best guesses, recorded instead of asking:**
  - **Avatar** is an https URL. Uploading an avatar image is 02-06's storage, and the per-Agent Theme avatar override is Operational Settings in spec 06, so this field is the Experience avatar only.
  - **Temperature** is 0 to 1, the range every registered chat provider accepts (Anthropic's maximum is 1).
  - **Limits:** max output tokens 1–8192; remembered turns 0–20; up to 6 starter questions; UI text up to 200 characters; rating prompt after 0–50 replies, where 0 means only at the end.
  - **UI text keys:** `send_button`, `rate_conversation` and `unavailable_message`, the three the spec names. More keys can be added with defaults.
  - **Guardrail defaults:** `block` and fail `closed`, the safe choices.
  - **Field names** `input_mode`, `classifier`, `fail_mode` and `refusal_text` follow spec 08's list.
  - **Picking a model:** choosing a credential asks for a model and saves nothing until one is chosen. This avoids silently picking a model.
  - **Deleted Tags:** deleting a Tag removes it from the Drafts that were scoped to it, rather than the save dropping unknown IDs without saying so. This way the Draft always shows its real scope. Agent Versions (spec 05) are snapshots and are left alone.
  - **A credential waiting for a model** is held only in the editor. If the Editor leaves the page before choosing a model, the saved setting stays as it was. The status says so while it waits ("Unsaved changes: choose a model.").
  - **Unpublished changes:** "changes not yet published" (user story 22) needs Versions, which arrive in spec 05. Until then the indicator shows the save state.
- **Sandbox limits:**
  - Images were built with `WITH_PDF=false BUNDLE_MODELS=false` and the egress proxy CA (`build.sh`), as earlier tickets did.
  - E2E ran against a compose project on moved ports (`compose.sandbox.yml`, now 41xxx: another ticket's stack held 46879).
  - Two transient failures under shared-machine load (one backend server-spawn test, one e2e Tag check) passed on rerun; see Results.
  - No real provider was called: the fake verifier and the fake gateway were used throughout.
