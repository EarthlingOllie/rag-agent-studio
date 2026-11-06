# Evidence: ticket 05-06, Playground Instructions picker

Branch `ticket/05-06-playground-instructions-picker`, from `origin/candidate` at `22b8cf6` (05-01, the blocker, merged as #46). The claim commit `768ca42`, the first on the branch, set Status `in-progress`. `origin/candidate` then moved to `3964965` (03-02, Close criterion-6 live-model gap; no migration) and was merged cleanly in `6a98d74`. This ticket's migration is `0026_playground_instructions`, revising `0025_instructions_versions`, so candidate keeps one Alembic head.

**Status: done.** Every criterion is met and evidenced below. The gaps at the end are what this sandbox can't run and best guesses recorded instead of asking.

## What was built

- **API** (`backend/app/playground/api.py`, `service.py`):
  - `sendPlaygroundMessage` takes an optional `instructions_version_id`. Left out or null, the answer follows the **Instructions Draft**, the default (as before). Set, it follows that **Instructions Version** of the Agent's Project, Current or not (an older or reverted Version works too). The Agent's Draft configuration is used either way, as the spec's runtime contract says ("the Draft AgentConfig plus the chosen Instructions").
  - A Version that isn't one of the Project's (another Project's, another Organisation's, or unknown) is refused with 422 "That Instructions Version isn't one of this Project's." before the question is saved, so nothing is recorded. A malformed ID is a 422 validation error.
  - The runtime from spec 04 is unchanged: it receives the chosen Instructions text in place of the Draft's.
- **Message attribution** (`backend/app/conversations/models.py`, migration `0026_playground_instructions`):
  - Each answer stores `instructions_source` (`draft`, the Draft marker, or `version`) and `instructions_version_id` (foreign key to the Version, `ON DELETE CASCADE`: Versions only go with their Project, which takes its Messages with it).
  - The migration backfills `draft` on every existing answer, since all of them ran with the Instructions Draft. The downgrade drops both columns.
  - `MessageOut` (conversation read), `TraceOut` and the stream's `done` event expose `instructions_source`, `instructions_version_id` and `instructions_version_number`. Questions carry nulls.
- **Studio** (`frontend/apps/studio/src/projects/AgentPage.tsx`, `TraceDrawer.tsx`, `agents.ts`):
  - The Playground has an **Instructions** picker. It offers "Instructions Draft" (selected by default), then every Version newest first, as `vN · note`, with `(Current)` on the Current Version. A hint says answers follow the Instructions Draft unless a Version is chosen. With no Versions, or if they can't be loaded, the hint says so and only the Draft is offered.
  - The choice applies to each question asked while it is selected, within the same Conversation.
  - Each answer shows "Instructions: Draft" or "Instructions: vN", taken from the `done` event (what the API says it ran with). The Trace drawer adds an **Instructions** row.
  - A 422 with a reason (a refused Version) shows that reason.
- **Generated API client** regenerated (`make gen-client`).
- **Glossary**: see criterion 4.

## Test seams

These follow the [shared test seams](../../../specs/README.md#shared-test-seams). The seams were not confirmed with a human (no human is available in this run); they are the ones the spec's Testing Decisions name: "Playground with a chosen Instructions Version" and "Message attribution to Version or Draft" at the API seam, the network seam for the Studio, and the end-to-end seam.

- **API seam:** `backend/tests/integration/test_playground_instructions.py` (8 tests). The chat model is a Pydantic AI `FunctionModel` echo, so the Instructions text that reached the model is read back from the answer, as the spec asks. Attribution is read back through the conversation and Trace APIs. The only table reads are counts after `erase_organisation` and a permanent Project deletion, which have no read API.
- **Network seam:** `frontend/apps/studio/src/projects/PlaygroundInstructions.test.tsx` (7 tests), with MSW. The agents fake (`src/test/agents.ts`) now answers with the Instructions it was asked with, and the existing Playground tests assert the new request field.
- **End-to-end seam:** `frontend/e2e/tests/playground-instructions.spec.ts`, Playwright against the docker compose stack (fake chat model), with axe.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | The picker offers the Instructions Draft (the default) or any Version | **API:**<br>• `test_by_default_the_playground_runs_the_instructions_draft`: with v1, v2 (Current) and an unpublished Draft, a question with the field left out and one with `null` both send the Draft ("Answer in Welsh.") to the model.<br>• `test_a_chosen_instructions_version_reaches_the_model_and_is_recorded`: in one Conversation, v1 (neither Draft nor Current), v2 (Current) and then the Draft each reach the model.<br>• `test_a_reverted_version_can_still_be_chosen`<br>• `test_only_this_projects_instructions_versions_can_be_chosen`: another Project's Version, another Organisation's Version and an unknown ID give 422 with the reason; a malformed ID gives 422; none of these questions is saved.<br>**Studio:**<br>• `the picker offers the Instructions Draft, the default, and every Version newest first`: options exactly "Instructions Draft", "v3 · Shorter", "v2 (Current) · Salaries", "v1 · First rules"; Draft selected.<br>• `a question is asked with the chosen Instructions, …`: exact request bodies (`instructions_version_id` null, v1, v2, null).<br>• `with no Versions published the picker offers only the Instructions Draft`<br>• `when the Versions can't be loaded the Playground still answers with the Instructions Draft`<br>• `a Version the API refuses is explained and the question isn't answered`<br>**E2E:** `playground-instructions.spec.ts` checks the options and the default in the real Studio, asks with the Draft then with v1, with axe scans. |
| 2 | Playground Messages record the Instructions Version or a Draft marker | **API:**<br>• `test_by_default_…`: the `done` event and the saved answer carry `instructions_source: "draft"` with null Version; the question carries nulls; `config_source` stays `draft`.<br>• `test_a_chosen_…`: answers read back as `("version", v1, 1)`, `("version", v2, 2)`, `("draft", None, None)`.<br>• `test_the_trace_names_the_instructions_an_answer_ran_with`<br>• `test_answers_saved_before_the_picker_are_marked_as_run_with_the_draft`: downgrades to `0025_instructions_versions`, upgrades to head, and the old answer reads back with the Draft marker.<br>• `test_permanently_deleting_the_project_removes_answers_that_name_its_versions` and `test_erasing_the_organisation_removes_answers_that_name_its_versions`: the new foreign key doesn't block 03-11's deletion or 10-01's `erase_organisation`.<br>`test_migrations.py` runs the full up/down/up round trip, and `test_the_migrations_match_the_models` runs `alembic check`.<br>**Studio:** each answer shows "Instructions: Draft" or "Instructions: vN" from the API's `done` event; the Trace drawer's Instructions row shows "v1" or "Draft" (two tests).<br>**E2E:** the answers show "Instructions: Draft" then "Instructions: v1", the Trace shows "v1", and the conversation API returns `[["draft", null], ["version", <v1 id>]]`. |
| 3 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | The seams are above. Backend `fail_under = 100` with branches: **100.00%**. Frontend Vitest: **100%** statements, branches, functions and lines. No coverage exclusions were added. See Results. |
| 4 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md` adds **Instructions picker** and **Draft marker**; **Message** and **Trace** now say a Playground answer records the Instructions it ran with. No ADR decision changed: ADR-0003 (immutable Versions) is untouched, since the picker only reads Versions. |

## Results

All runs are local, one suite at a time (GitHub Actions is down; the user authorised merging on local results), at `6a98d74`, the merge of `origin/candidate` at `3964965`, from a clean working tree. The commits after `6a98d74` change only this folder and the ticket's Status. The backend ran against fresh `rag0506-*` containers on host ports 47832 (Postgres), 47879 (Redis) and 47891 (RustFS), which no other ticket uses.

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `make test-backend` | **1669 passed**, 7 deselected (live); coverage **100.00%** lines and branches | [backend-tests.log](backend-tests.log) |
| Frontend tests + coverage gate | `make test-frontend` | **41 files, 513 tests passed**; 100% statements, branches, functions and lines | [frontend-tests.log](frontend-tests.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc) | exit 0 | [lint.log](lint.log) |
| API client drift | `make check-client` | "API client is up to date." | [client-drift.log](client-drift.log) |
| Security | gitleaks (`origin/candidate..HEAD`), `make audit` (pip-audit, pnpm audit) | no leaks, no known vulnerabilities | [security.log](security.log) |
| Images | `build.sh` (sandbox `make images`) | both images built (`rag-agent-studio/api:0506`, `rag-agent-studio/studio:0506`), exit 0 | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` (project `rag0506`) | **64 passed** on the first attempt (3.7 min), including `playground-instructions.spec.ts` with its axe scans, and the existing `playground.spec.ts` and `instructions-versions.spec.ts` | [e2e.log](e2e.log) |
| Infra | terraform checks | not run: this ticket changes no infra | n/a |

## Gaps and best guesses

- **Sandbox build settings:** PDF conversion and bundled models are off in the sandbox images (Hugging Face is blocked), as in earlier tickets. Trivy (`make image-scan`) was not run; this ticket adds no dependency or image change. Infra checks were not run; this ticket changes no infra.
- **Seams not confirmed with a human:** recorded above; they follow the spec's Testing Decisions.
- **Best guesses, recorded instead of asking:**
  - **The choice is per question**, not per Conversation: the picker can change between questions and each answer records its own choice. This lets an Editor compare Instructions side by side in one Conversation; a Playground reset is still available for a clean slate.
  - **Remembered turns** are sent to the model as they were said, whatever Instructions produced them; only the system Instructions change with the picker.
  - **Unknown Version → 422**, not 404: the Version is named in the request body, so it is a validation failure of the request, and the route's resources (Project, Agent, Conversation) do exist.
  - **The Draft marker is `instructions_source: "draft"`** with a null Version, alongside the existing `config_source: "draft"` for the Agent's configuration. Visitor answers (spec 06) will have their Instructions derivable from the Agent Version, as the spec says; this ticket stores the Instructions explicitly on Playground answers.
  - **Existing answers are backfilled with the Draft marker**, since the Playground only ran the Instructions Draft before this ticket.
