# Evidence: ticket 04-09, Agent Archive and delete

Branch `ticket/04-09-agent-archive-delete`, from `origin/candidate` at `a123fa1` (03-11 #40 merged; 04-01, the only blocker, done). The claim commit `9f059ec`, the first on the branch, set Status `in-progress`. Every check below ran on `57e49b4`; `origin/candidate` had not moved since the branch was cut.

**Status: done.** Every criterion is met and evidenced below. Best guesses made instead of asking are listed at the end.

## What was built

- **API** (`backend/app/agents/api.py`, `service.py`):
  - `POST …/agents/{agent_id}/archive` (`archiveAgent`, Editors and Owners). Sets `archived_at`, records `agent.archived` (before/after `{name, archived}`). An archived Agent gives 409 "This Agent is archived. An Owner can restore it."
  - `POST …/agents/{agent_id}/restore` (`restoreAgent`, Owners only, 403 otherwise). Records `agent.restored`. An active Agent gives 409 "This Agent isn't archived."
  - `DELETE …/agents/{agent_id}` with `{confirm_name}` (`deleteAgent`, Owners only), 204. Only an archived Agent (409 "Only an archived Agent can be deleted. Archive it first."), and only with its name typed exactly (400 "Type the Agent's name exactly to delete it."). It records `agent.deleted` with `before = {name, project_id, public_id, conversation_count}` and deletes the Agent in the same transaction. The foreign keys' `ON DELETE CASCADE` take its Draft, Conversations, Messages and Message retrievals (Trace rows). Its Credential references (computed from Drafts) go with the Draft.
  - `GET …/agents` lists active Agents only; `?archived=true` lists archived ones. `GET …/agents/{id}` still opens an archived Agent, so its history stays readable.
  - An archived Agent's Draft can't be saved (409), and the Playground refuses it: starting a Conversation and sending a message give 409 with the same message (`active_agent` in `service.py`, used by `app/playground/service.py`). Reading its existing Playground Conversations and Traces still works.
  - In an archived Project, archive, restore and delete of its Agents are refused with the Project's 409.
- **Studio** (`frontend/apps/studio/src/projects/`):
  - `AgentsTab.tsx`: active Agents only, with "Show archived Agents" switching to the archived list (with its archive date). A `?deleted=` notice says "<name> was deleted permanently."
  - `AgentPage.tsx`: "Archive Agent" with a confirmation. An archived Agent shows an "Archived" notice. Owners get "Restore <name>" and "Delete permanently", which asks for the name typed exactly before its button enables, then returns to the Agents tab. The Playground is hidden while archived.
  - `DraftEditor.tsx`: an archived Agent's Draft is read only. Every settings group (`fieldset`) and the markdown system prompt are disabled; the status reads "Read only while archived."
  - `agents.ts`: `useAgents(…, archived)`, `useArchiveOrRestoreAgent`, `useDeleteAgent`. The API client is regenerated.

## Test seams

The [shared test seams](../../../specs/README.md#shared-test-seams) the spec names. No human was available to confirm them, so those were used:

- **API seam** (in process, real Postgres with pgvector and Redis, fake chat model): `backend/tests/integration/test_agent_archive.py` (new, 16 tests), plus the three new routes in `test_tenant_isolation.py` and `test_openapi.py`. Only the deleted Agent's Conversation rows are read directly (`conversation_rows`, from 03-11's tests), because once the Agent is gone they have no API surface.
- **Frontend network seam (MSW):** `frontend/apps/studio/src/projects/AgentArchive.test.tsx` (new, 10 tests). The fake Agents API in `src/test/agents.ts` now filters by `archived` and serves archive, restore and delete.
- **End-to-end** against the docker compose stack with the fake gateway: `frontend/e2e/tests/agent-archive.spec.ts` (new), with axe scans.

Tests were written first and seen failing (404 for the routes; missing UI) before each implementation.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Archive and restore work, and archived Agents are excluded from lists and the Playground | **API** (`test_agent_archive.py`):<br>• `test_an_editor_archives_an_agent_and_it_leaves_the_list`: 200 with `archived_at` = the clock; the list holds only the other Agent, `?archived=true` holds it, its page still opens.<br>• `test_an_archived_agent_cannot_be_archived_again_or_have_its_draft_changed` (409, Draft unchanged).<br>• `test_archiving_blocks_the_playground_but_keeps_its_conversations`: starting and asking give 409 "This Agent is archived…"; the earlier Conversation and its Trace read back unchanged.<br>• `test_an_owner_restores_an_archived_agent`: an Editor gets 403; the Owner restores, it is listed again and the Playground answers.<br>• `test_only_an_archived_agent_can_be_restored`, `test_an_archived_projects_agents_cannot_be_archived_restored_or_deleted`, `test_agents_of_another_project_are_not_found`.<br>• `test_tenant_isolation.py`: archive (Editor), restore (Owner) and delete (Owner) are 404 from other Organisations and 403 for Editors on Owner routes.<br>**Frontend** (`AgentArchive.test.tsx`): `archived Agents are left out of the Agents list and shown on request`, `a Project with no archived Agents says so`, `an Editor archives an Agent after confirming; its page turns read-only without the Playground`, `a refused archive shows why`, `an Owner restores an archived Agent and the Playground returns`, `a refused restore shows why`, `Editors see no restore or delete on an archived Agent`, `a Playground refused because the Agent was archived elsewhere says so`.<br>**E2E** (`agent-archive.spec.ts`): archive in the browser; the Playground disappears, the Draft is read only, the Agents list holds only the other Agent and the archived list holds it; restore brings the Playground back. |
| 2 | Owners can permanently delete after typing the name, which cascades | **API:**<br>• `test_an_owner_permanently_deletes_an_archived_agent_after_typing_its_name`: 204, the Agent is 404, gone from both lists, the other Agent stays.<br>• `test_deletion_cascades_to_the_draft_conversations_and_credential_references`: before, 2 Conversations, 2 Messages and 1 Message retrieval; after, 0 of each, both Conversations 404. The Anthropic credential its Draft used as Model override was refused deletion (409) before, and deletes (204) after.<br>• `test_deletion_needs_the_name_typed_exactly` (5 cases: empty, other case, trailing space, double space, another name): 400, nothing deleted.<br>• `test_only_an_archived_agent_can_be_deleted` (409), `test_editors_cannot_delete_an_agent` (403).<br>**Frontend:** `an Owner deletes an archived Agent permanently after typing its name` (button disabled until exact, lands on the Agents tab with the notice), `deleting can be cancelled, and a refusal shows why`.<br>**E2E:** the confirm button stays disabled for "old helper", deletes for "Old helper"; the notice shows and both lists no longer hold it. |
| 3 | Everything is recorded as Audit Events | **API:** each test above asserts its event exactly: `agent.archived` and `agent.restored` (actor, target `{type: agent, id}`, before/after `{name, archived}`, `occurred_at` = the controllable clock), `agent.deleted` (actor, target, `before = {name, project_id, public_id, conversation_count}`, `after = null`). Refused actions record nothing (`audit_events(...) == []` / count unchanged). `agent.created` was already recorded by 04-01.<br>**E2E:** the Audit tab shows `agent.archived` twice, `agent.restored` and `agent.deleted` once each. |
| 4 | Tests at the highest seam; 100% line and branch coverage holds | Seams above. Backend gate `fail_under = 100` with branches, and the Vitest gate at 100% statements, branches, functions and lines: see Results. |
| 5 | New domain terms in `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md`: **Archive** now says what archiving an Agent does and that any Member can; **Restore** and **Permanent deletion** now cover Agents (deleting an Agent takes its Draft and Conversations and releases its Credential references). No new term and no ADR change: this follows the Project's Archive / Restore / Permanent deletion decisions. |

## Results

All runs are local and sequential (`checks.sh`), at `57e49b4`. GitHub Actions is down; the user authorised merging on local results.

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `make test-backend` against the `rag0409-pg` (pgvector), `rag0409-redis` and `rag0409-rustfs` containers | **1543 passed**, 7 deselected (live); coverage **100%** lines and branches (7156 statements, 794 branches) | [backend-tests.log](backend-tests.log) |
| Frontend tests + coverage gate | `make test-frontend` | **39 files, 480 tests passed**; 100% statements, branches, functions and lines | [frontend-tests.log](frontend-tests.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc) | exit 0 | [lint.log](lint.log) |
| API client drift | `make check-client` | "API client is up to date." | [client-drift.log](client-drift.log) |
| Security | `make audit` (pip-audit, pnpm audit); gitleaks over this branch's commits | no known vulnerabilities, no leaks | [security.log](security.log), [secret-scan.log](secret-scan.log) |
| Images | `build.sh` (sandbox `make images`) | both built | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` (project `rag0409`) | **58 passed**, including `agent-archive.spec.ts`, `playground.spec.ts` and `agent-config.spec.ts` | [e2e.log](e2e.log) |
| Infra | not run | this branch changes nothing under `infra/` | |

## Gaps and best guesses

- **Best guesses, recorded instead of asking:**
  - **Restore is Owners only**, as the ticket says ("Owners can restore them") and as for Projects; archiving is any Member (Editor).
  - **Deletion is synchronous** (204), unlike the Project's background cascade: an Agent has no stored files, and the database cascade is one transaction.
  - **An archived Agent's Draft is read only** (409 on save), so an archived Agent can't change while it is retired; restore it to edit. Its Playground history stays readable.
  - **In an archived Project**, its Agents can't be archived, restored or deleted (the Project's 409); deleting the Project removes them.
  - **The Project's `agent_count`** still counts archived Agents (it is what the Project holds, and 03-11's deletion audit relies on it); only the lists exclude them.
  - **Credential references stay while archived**: an archived Agent can be restored with its Draft, so its credentials remain protected until it is deleted.
  - Serving to Visitors (spec 06) doesn't exist yet; when it does it must refuse archived Agents too (the Glossary's Archive says it stops serving).
- **Sandbox limits:** images built with `WITH_PDF=false BUNDLE_MODELS=false` and the egress proxy CA (`build.sh`); e2e ran on the `rag0409` compose project on moved ports (`compose.sandbox.yml`, 47xxx). No real provider was called: fake verifier and fake gateway throughout. GitHub Actions is down; the user authorised merging on local results.
