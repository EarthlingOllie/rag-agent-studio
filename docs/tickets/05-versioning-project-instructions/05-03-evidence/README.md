# Evidence: ticket 05-03, Revert via Live History

Branch `ticket/05-03-revert-live-history`, from `origin/candidate` at `0e5ef28` (05-02, Publish Agent to Live Version, merged as #48). The claim commit, the first on the branch, set Status `in-progress`. The feature is `27a1292`. `origin/candidate` then moved to `be524a3` (05-06, Playground Instructions picker, #49); it was merged in cleanly as `282e0c5` (no conflicts; 05-06's migration 0027 follows 05-02's 0026 and this ticket adds none) and every check was run again on the merge. This ticket adds no migration: the `revert` action value and the Live History table came with 05-02.

**Status: done.** Every criterion is met and evidenced below. The gaps at the end are scope left to later tickets on purpose, plus what this sandbox can't run.

## What was built

- **The revert rule** (`backend/app/agents/versions.py`, written down in the module docstring): the revert target is the from-Version of the Live History entry that moved Live onto the present Live Version by a publish (or bulk publish). Revert entries aren't followed, so publish → revert → revert walks further back instead of toggling. This is a stack: each publish pushes a new Version (a Version is pushed once, when it's created) and each revert pops one.
  - When there's no such from-Version (the Agent is not live, or its Live Version was its first), the revert is refused: `NothingToRevertError`.
  - When the target names a Provider Credential that is gone or no longer offers its model, it is refused: `RevertTargetInvalidError`. 05-02 noted that only the Draft's and the Live Version's credentials are protected from deletion; this check closes that gap.
  - Otherwise, under the Agent row lock (`SELECT … FOR UPDATE`, as for publish), the Live Version pointer moves to the target, a `revert` Live History entry (from the old Live Version to the target, actor, time) is written and `agent.reverted` is audited, in one transaction.
  - The Draft is untouched and no Version is created. Since the Live Version carries its config and pinned Instructions Version, the serving contract (`app.agents.serving`) serves both from the target straight away.
- **Credential check** (`backend/app/agents/validation.py`): `credential_problems` is the credential half of `check_draft`, split out so that revert can use it. It share-locks the credentials, as before.
- **API** (`backend/app/agents/versions_api.py`): `POST …/agents/{id}/revert` (`revertAgent`), for Editors and Owners, scoped by Organisation through the one policy dependency. It returns 200 with the Version that is Live again. It returns 409 with "There's no earlier Live Version to revert to.", the credential refusal, or the archived Agent or Project refusal, and 404 outside the Organisation.
- **Studio** (`frontend/apps/studio/src/projects/AgentLiveHistory.tsx`, hooks in `agents.ts`): the Agent page has a **Live History** section:
  - **Timeline:** a list of every change, newest first. Each row shows "Published v1 → v2", "Reverted v3 → v2", "Bulk published …" or "Bulk reverted …", then who and when.
  - **Revert to vN:** the target is worked out from the timeline with the same rule. Clicking it asks for confirmation ("Revert to v2? Visitors are served v2 with the Instructions it pins at once. The Draft isn't changed."), with Cancel. Afterwards it reports "Reverted to v2 with Instructions v1. It is now Live." The badge changes to Live v2 and the timeline gains the revert row.
  - **Nothing to revert to:** the page says "There's no earlier Live Version to revert to: v1 was the first." and shows no button.
  - **Never published:** the page says "Nothing has been Live yet."
  - **Archived Agents:** the timeline is shown with no Revert button.
  - **Refusals:** the API's reason is shown.
- The **generated API client** was regenerated (`make gen-client`).

## Test seams

These follow the [shared test seams](../../../specs/README.md#shared-test-seams) and the spec's Testing Decisions. They were not confirmed with a human; they are the seams 05-02 used for the same module.

- **API seam:** `backend/tests/integration/test_agent_revert.py` (9 tests, 18 cases) drives the app in process against real Postgres and Redis. It asserts on HTTP responses and what reads back through the API (Agent, Versions, Live History, Audit Events). The one exception is the restore test: no API serves Visitors until 06-01, so it calls the serving module (the runtime contract) with the echoing `FunctionModel`, through 05-02's `serve` helper.
  - `test_tenant_isolation.py` adds the route: other Organisations get 404, unauthenticated requests get 401, and Editors are allowed.
  - `test_openapi.py` lists `revertAgent`.
- **Network seam:** `frontend/apps/studio/src/projects/AgentLiveHistory.test.tsx` (11 tests). The `fakeAgentsApi` MSW fake gains a stateful Live History that publish and revert append to.
- **End-to-end seam:** `frontend/e2e/tests/agent-revert.spec.ts`, Playwright against the docker compose stack, with axe.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Revert follows the Live History, verified by a table-driven test of action sequences including publish → revert → revert | `test_revert_follows_the_live_history`, 10 parametrised sequences of P (publish) and R (revert), each with the expected Live Version number after every action, and `-` for a refused revert. The expected numbers are worked out by hand from the spec. They include:<br>• `P P P R R` → `1 2 3 2 1` (publish → revert → revert walks back, no toggle)<br>• `P P R P R` → `1 2 1 3 1` (a Version published and reverted is skipped)<br>• `P P P R P R R` → `1 2 3 2 4 2 1`<br>• `P P P R R P P R R R` → `… 4 1 -`<br>Each case also checks that the Live History holds exactly the publishes and reverts that happened, in order, chained (each entry's from-Version is the previous entry's to-Version).<br>`test_a_revert_is_written_to_the_live_history`: from, to, `revert`, actor (an Editor), no bulk operation; no Version is created.<br>`test_concurrent_reverts_each_step_back_once`: 4 parallel reverts from v4 give exactly v3, v2, v1 and one 409.<br>**Studio:** "reverting again follows the Live History further back instead of toggling" and "a Version published and then reverted is skipped".<br>**E2E:** v1 → v2 → revert gives v1, read back through the API. |
| 2 | Revert is refused when there's nothing to revert to | `test_nothing_to_revert_to_is_refused_and_changes_nothing`: a never-published Agent and an Agent with only v1 both get 409 "There's no earlier Live Version to revert to." Live, the Live History and the Audit log are unchanged. The table's `-` cases refuse after walking back to v1.<br>Other refusals: `test_an_archived_agent_or_project_cannot_be_reverted`, `test_revert_is_not_found_outside_the_organisation`, `test_a_version_whose_credential_is_gone_cant_be_made_live_again`.<br>**Studio:** "the Editor is told when there's nothing to revert to" (message, no button), "an Agent that has never been Live…", and "a refused revert (409/500) says why".<br>**E2E:** the message is shown at v1, and a further `POST /revert` returns 409 with that detail. |
| 3 | Revert restores both config and pinned Instructions (verified with an echoing `FunctionModel`) | `test_revert_restores_the_earlier_config_and_its_pinned_instructions`. v1 has prompt "First prompt.", the Default Model (gpt-4.1-mini) and Instructions v1 "First rules.". v2 has "Second prompt.", gpt-4.1 and Instructions v2 "Second rules.". With v2 Live, the echo model receives v2's Instructions and prompt and the gateway builds `openai:gpt-4.1`. After the revert, the API returns v1 pinning Instructions v1. The echo model then receives the preamble, "First rules." and "First prompt.", the gateway builds `openai:gpt-4.1-mini`, and the answer is attributed to v1 (`config_source` `version`). The Draft still holds v2's edits.<br>**E2E:** after the revert the Live Version pins Instructions v1, and the Studio says "Reverted to v1 with Instructions v1". |
| 4 | A Live History timeline is shown in the UI, and reverts are audited | **Timeline:** `AgentLiveHistory.test.tsx`:<br>• "the Live History timeline lists every change…": all four action labels, moves, actors, times, newest first<br>• "publishing adds the move to the timeline"<br>• "reverting asks for confirmation…": Cancel sends nothing; confirming adds "Reverted v3 → v2" and changes the badge<br>• archived (timeline, no button) and load-error states<br>**E2E:** `agent-revert.spec.ts` checks the timeline rows before and after the revert, with axe scans with the confirmation open and after the revert.<br>**Audit:** `test_a_revert_is_recorded_as_an_audit_event`: `agent.reverted`, exact actor (Owner and Editor), target, before `{live_version: {version_id, number}}`, after `{live_version: {version_id, number, instructions_version}}`, for two consecutive reverts. Refused reverts record nothing (criterion 2's tests). The E2E reads `agent.reverted` before/after = `[[2, 1]]` from the Audit API. |
| 5 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | The seams are listed above. The coverage gates are in the results below: backend `fail_under = 100` with branches, and frontend Vitest at 100% for every metric. No coverage exclusions were added. |
| 6 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md`:<br>• **Live History** now gives the revert rule (with the v1, v2, v3 example) and names the Live History timeline.<br>• **Revert** now says that an Agent revert restores config and pinned Instructions, when it is refused, and that it never creates, edits or deletes a Version or changes the Draft. The old text said "Reverting steps back one entry", which the rule replaces.<br>No ADR decision changed: ADR-0003 (immutable Versions, a movable Live pointer) is followed as written. |

## Results

All runs are local, one suite at a time (GitHub Actions is down; the user authorised merging on local results). Every check ran at `282e0c5` (the merge of `origin/candidate` `be524a3`) with no uncommitted code changes; only this folder and the ticket file were being written. Each log's first line names the command and the commit.

| Check | Command | Result | Log |
|---|---|---|---|
| Install | `make install` | exit 0 | [install.log](install.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc) | exit 0 | [lint.log](lint.log) |
| API client drift | `make check-client` | "API client is up to date." | [client-drift.log](client-drift.log) |
| Backend tests + coverage gate | `make test-backend` against fresh `rag0503-svc` Postgres/pgvector, Redis and RustFS containers (ports 48632/48679/48691); OpenTelemetry span lines filtered out | **1755 passed**, 7 deselected (live); coverage **100.00%** lines and branches | [backend-tests.log](backend-tests.log) |
| Frontend tests + coverage gate | `make test-frontend` | **43 files, 535 tests passed**; 100% statements, branches, functions and lines | [frontend-tests.log](frontend-tests.log) |
| Images | `build.sh` (sandbox `make images`) | both images built (`rag-agent-studio/api:0503`, `rag-agent-studio/studio:0503`), exit 0; removed afterwards | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` (project `rag0503-e2e`, host ports 49310–49825) | **66 passed** on the first attempt (3.8 min), including `agent-revert.spec.ts` with its axe scans | [e2e.log](e2e.log) |
| Security | gitleaks (`origin/candidate..HEAD`), `make audit` (pip-audit, pnpm audit) | no leaks, no known vulnerabilities | [security.log](security.log) |
| Infra | terraform checks | not run: this ticket changes no infra | n/a |

## Gaps and best guesses

- **Out of this ticket's scope, left to the tickets named:**
  - Bulk revert, and the Instructions revert's offer to bulk-revert Agents pinned to the reverted Version (05-05). The rule already follows `bulk_publish` entries, and the timeline labels bulk actions.
  - The Version list panel and diffs (05-04).
  - A Visitor-facing route (06-01). Serving after a revert is tested through the `app.agents.serving` module, as in 05-02.
  - The spec's end-to-end scenario (Instructions v2 bulk-adopted by one of two Agents, then reverted) needs bulk publish (05-05). This ticket's E2E does the single-Agent version: publish with Instructions v1, publish with v2, revert, and v1 with Instructions v1 is Live.
- **Best guesses, recorded instead of asking:**
  - **The rule ignores revert entries.** The spec's wording, "the from-Version of the most recent entry that moved Live onto the current Version", would make a second revert follow the first revert's entry back and toggle. The spec says the second revert must "follow the history further back rather than toggling", so only publish and bulk publish entries are followed. The module docstring and `GLOSSARY.md` record this.
  - **The Draft is left alone** on revert, as for Instructions in 05-01. Discarding the Draft back to Live is 05-04's action.
  - **Archived Agents and Projects can't be reverted** (409), as for publish. Their timeline stays readable.
  - **A revert whose target's credential is gone is refused** (409) rather than serving a configuration that can't run. The Editor can publish a fixed Version instead.
  - **The Studio works out the target** from the timeline to name it ("Revert to v2") and to say upfront that there's nothing to revert to (story 14). The API applies the rule itself and has the final say. Any refusal it returns is shown.
- **Sandbox limits** (as in earlier tickets):
  - Images are built with `WITH_PDF=false BUNDLE_MODELS=false` (`build.sh` adds only the egress proxy CA), and the e2e stack runs `EMBEDDER=fake`, because Hugging Face is blocked here.
  - The live suite and the Trivy image scan were not run.
  - Infra checks were not run; this ticket changes no infra.
