# Evidence: ticket 05-01, Project Instructions Versions

Branch `ticket/05-01-project-instructions-versions`, from `origin/candidate` at `cb228e6` (04-02, the blocker, merged). The claim commit, the first on the branch, set Status `in-progress`. `origin/candidate` then moved three times and was merged each time: `c3e8db7` (08-04, Canary token, migration `0021`), `f0d632d` (02-06, Theme logo and avatar, migration `0022`) and `00f8214` (10-01, Seed foundation, migration `0023_erase_organisation`). This ticket's migration is therefore `0024_instructions_versions`, revising `0023_erase_organisation`, so candidate keeps one Alembic head.

**Status: done.** Every criterion is met and evidenced below. The gaps at the end are scope this ticket leaves to later tickets on purpose, plus what this sandbox can't run.

## What was built

- **Data** (`backend/app/projects/models.py`, migration `0024_instructions_versions`):
  - `projects.instructions` is now the **Draft**. Its GET and PUT routes and the `project.instructions_updated` Audit Event are unchanged.
  - `project_instructions_versions`: number (1, 2, 3… per Project, unique per Project), markdown, note, author (a Member; null only for a migrated v1), created time, and `previous_version_id`, the Version that was Current when this one was published. A trigger refuses every `UPDATE`, so Versions are immutable even to direct SQL. Rows still go with their Project (cascade delete), and with their Organisation when 10-01's `erase_organisation` (`make seed-reset`) erases it.
  - `projects.current_instructions_version_id`: the **Current Version** pointer.
  - The migration makes a v1 from every non-empty Instructions field and points Current at it. The Draft keeps the same text, so what Agents follow doesn't change. Empty Instructions get no Version. The downgrade drops the Versions and the pointer and keeps the Draft.
- **Service** (`backend/app/projects/instructions.py`, rule written in its docstring):
  - **Publish** locks the Project row (`SELECT … FOR UPDATE`) and allocates the next number inside the lock. It freezes the Draft with a note and makes it Current. A Draft that equals the Current Version (or is empty before the first publish) is refused, so a duplicate or concurrent double publish gives a clear conflict.
  - **Revert** moves Current back to the Version that was Current when the present one was published. Reverting again keeps walking back that chain, so it never toggles, and a reverted Version is skipped. With nothing before, revert is refused. The Draft is never touched.
  - Both record an Audit Event in the same transaction: `project.instructions_published` (before `{current_version}`, after `{current_version: {version_id, number, note}}`) and `project.instructions_reverted` (before and after `{current_version: {version_id, number}}`). The target is the `project`.
- **API** (`backend/app/projects/instructions_api.py`). The routes are for Editors and Owners, scoped by Organisation through the one policy dependency. An archived Project is readable; publish and revert return 409 there.
  - `GET …/projects/{id}/instructions/versions` (`listProjectInstructionsVersions`): `{current_version_id, versions}`, newest first.
  - `POST …/instructions/versions` (`publishProjectInstructions`), body `{note}` (1–500 characters, trimmed): returns 201 with the new Version. A 409 means nothing to publish or an archived Project.
  - `POST …/instructions/revert` (`revertProjectInstructions`): returns 200 with the Version that is now Current. A 409 means nothing to revert to or an archived Project.
  - No route changes or deletes a Version.
- **Studio** (`frontend/apps/studio/src/projects/InstructionsVersions.tsx`, under the editor on the Project's Instructions tab):
  - The **Publish Instructions** form takes a required note. It saves the Draft exactly as written in the editor, then publishes it and shows "Published vN". If the Draft save is refused, the message says the Draft could not be saved, so nothing was published, and why (for example the 20,000-character limit); the note message appears only for a refused note.
  - The **Versions** history: "Current Version: vN", then each Version newest first. Each shows its number, a **Current** badge, the note, the author (or "No author") and the UTC time, with the markdown behind **Show the Instructions**.
  - **Revert to vN**, with a confirmation that says the Draft isn't changed. It then shows "Reverted to vN". Only the outcome of the latest publish or revert shows: publishes and reverts share a mutation key, and each status hides once the other has been submitted since.
  - An archived Project shows the history with no publish form and no revert.
- The **generated API client** was regenerated (`make gen-client`).

## Test seams

These follow the [shared test seams](../../../specs/README.md#shared-test-seams). The seams were not confirmed with a human; they are the ones the spec's Testing Decisions name.

- **API seam:** `backend/tests/integration/test_project_instructions_versions.py` (27 tests) runs the app in process against real Postgres and Redis. It asserts only on HTTP responses and what reads back through the API, including the Audit API. The exceptions are the one defence-in-depth direct `UPDATE` and the migration test, which moves the schema with Alembic.
- `test_tenant_isolation.py` adds the three routes: Members of another Organisation get 404 and an unknown Organisation gets 404 (both "Not found"); unauthenticated requests get 401; Editors are allowed.
- `test_openapi.py` lists the three new operations.
- **Network seam:** `frontend/apps/studio/src/projects/InstructionsVersions.test.tsx` (15 tests), with the `fakeProjectsApi` MSW fake extended with a stateful Versions store.
- **End-to-end seam:** `frontend/e2e/tests/instructions-versions.spec.ts`, Playwright against the docker compose stack, with axe.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Instructions have a Draft, immutable numbered Versions and a Current Version pointer | **Draft:** `projects.instructions`. **Versions:** `project_instructions_versions`, unique `(project_id, number)`, with an UPDATE-refusing trigger. **Pointer:** `projects.current_instructions_version_id`.<br>**Tests:**<br>• `test_publishing_the_draft_makes_v1_the_current_version`<br>• `test_each_publish_adds_the_next_version_and_the_history_lists_them_newest_first`: editing the Draft afterwards changes no Version.<br>• `test_a_new_project_has_no_versions`<br>• `test_versions_cannot_be_changed_through_the_api`: PUT, PATCH and DELETE on the collection give 405, and on an item 404. The Version is unchanged.<br>• `test_the_database_refuses_to_change_a_version`: a direct `UPDATE` raises "immutable".<br>• `test_concurrent_publishes_of_one_draft_make_one_version_and_a_clear_conflict`: parallel requests give one 201 and one 409, with one Version.<br>• `test_concurrent_publishes_of_different_drafts_get_consecutive_numbers`: no duplicate or skipped numbers.<br>• `test_erasing_the_organisation_removes_its_published_versions`: with Versions by two authors, a revert, and a Version whose previous Version is an earlier one, `erase_organisation` still succeeds. The cascade deletes rows and never updates one, so the immutability trigger doesn't fire, and no Version of the Organisation is left. |
| 2 | A migration turns the existing Instructions field into the Draft plus a v1, and the data is asserted | Migration `backend/migrations/versions/20261106_0024_instructions_versions.py`.<br>`test_the_migration_turns_existing_instructions_into_the_draft_and_v1`:<br>• It saves Instructions through the API, downgrades to `0023_erase_organisation` (spec 04's single Instructions field) and upgrades to head.<br>• Through the API it asserts v1 = the old text, Current, no author, the migration note, and no previous Version. The Draft is unchanged. A Project with empty Instructions has no Versions.<br>• It then publishes v2 on top (previous = v1) and reverts back to the migrated v1.<br>`test_migrations.py` runs the full up/down/up round trip, and `test_the_migrations_match_the_models` runs `alembic check`. |
| 3 | Publishing takes a note; the history is listed; revert moves the Current Version back | **Publishing takes a note:**<br>• `test_publishing_takes_a_note`: a missing, empty, whitespace-only or 501-character note gives 422 and no Version.<br>• `test_the_note_is_trimmed`<br>• `test_a_draft_that_matches_the_current_version_is_not_published`<br>• `test_clearing_the_instructions_can_be_published`<br>**History:** `test_each_publish_adds_…` checks number, markdown, note, author, previous Version, order and created time.<br>**Revert:**<br>• `test_revert_moves_the_current_version_back_along_its_history`: a table of 5 action sequences, including revert-twice-walks-back, reverted-version-is-skipped and walks-the-chain-not-the-numbers.<br>• `test_revert_returns_the_version_it_moved_to_and_leaves_the_draft_alone`<br>• `test_revert_with_nothing_before_the_current_version_is_refused`: never published, only v1, and walked back to the start.<br>• `test_an_archived_projects_versions_can_be_read_but_not_changed`<br>• `test_versions_are_not_found_outside_their_organisation`<br>**Studio:** `InstructionsVersions.test.tsx` covers:<br>• the history (order, Current badge, note, author or "No author", UTC time, the markdown shown, "(empty)")<br>• unpublished state<br>• publishing saves the Draft as written, then publishes with the note (exact request bodies), and the history updates<br>• the note is required with max 500<br>• 409 and 422 messages; a refused Draft save doesn't publish, and a 422 on the Draft save names the save, not the note; progress and generic failure<br>• revert with confirmation (status, new Current, button gone at v1)<br>• cancel; a refused revert; archived read-only; load failure<br>• only the latest publish or revert shows its outcome (revert, publish, revert)<br>**E2E:** `instructions-versions.spec.ts` publishes v1 and v2 with notes in the real Studio, browses the history, reverts to v1 (the Draft is unchanged) and checks the API. |
| 4 | Publish and revert are recorded as Audit Events | `test_publish_and_revert_are_recorded_as_audit_events`: exact actor, before and after (Version ID, number, note) and target for two publishes and one revert. `test_refused_publishes_and_reverts_record_nothing`. The E2E reads `project.instructions_published` = [2, 1] and `project.instructions_reverted` = [1] from the Audit API. |
| 5 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | The seams are above. The coverage gates are in the results below: backend `fail_under = 100` with branches, and frontend Vitest at 100% for every metric. No coverage exclusions were added. |
| 6 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md`:<br>• adds **Instructions Version** and **Revert**<br>• **Current Version** gains the revert rule<br>• **Version** notes the note and per-owner numbering<br>• **Project Instructions** names its Draft, Versions and Current Version<br>No ADR decision changed. ADR-0003 (immutable Versions, a movable pointer, reverting walks history rather than numbers) is followed as written. |

## Results

All runs are local, one suite at a time (GitHub Actions is down; the user authorised merging on local results). Every check ran at `bb29854`, which is on top of the merge of `origin/candidate` at `00f8214` (10-01) and holds the round-2 fixes: migration `0024_instructions_versions` after `0023_erase_organisation`, the erasure test, the refused-Draft-save message and the latest-outcome-only status. The next commit changes only this folder. Every log's first line names the commit it ran at.

Earlier runs at `f63d874` (after 08-04) and `7521221` (after 02-06) also passed, the first after an environment rerun; their logs were superseded by the runs below.

| Check | Command | Result | Log |
|---|---|---|---|
| Backend tests + coverage gate | `make test-backend` against fresh `rag0501-*` Postgres/pgvector, Redis and RustFS containers | **1529 passed**, 7 deselected (live); coverage **100.00%** lines and branches | [backend-tests.log](backend-tests.log) |
| Frontend tests + coverage gate | `make test-frontend` | **39 files, 481 tests passed**; 100% statements, branches, functions and lines | [frontend-tests.log](frontend-tests.log) |
| Lint and type-check | `make lint` (ruff check, ruff format --check, mypy --strict, eslint, tsc) | exit 0 | [lint.log](lint.log) |
| API client drift | `make check-client` | "API client is up to date." | [client-drift.log](client-drift.log) |
| Security | gitleaks (`origin/candidate..HEAD`), `make audit` (pip-audit, pnpm audit) | no leaks, no known vulnerabilities | [security.log](security.log) |
| Images | `build.sh` (sandbox `make images`) | both built | [images.log](images.log) |
| End-to-end | `make e2e` with `compose.sandbox.yml` (project `rag0501`) | **57 passed** on the first attempt, including `instructions-versions.spec.ts` with its axe scans, and `instructions.spec.ts` | [e2e.log](e2e.log) |
| Infra | terraform checks | not run: this ticket changes no infra | n/a |

## Gaps and best guesses

- **Out of this ticket's scope, left to the tickets named:**
  - Agent Versions, the Live Version and pinning an Instructions Version (05-02); the Live History table (05-02 and 05-03).
  - Diffs between Instructions Versions and Draft management, such as the 409 on a stale Draft save (05-04).
  - Opening the bulk dialog after publishing, Instructions revert offering bulk revert candidates, and "N Agents behind" (05-05).
  - The Playground Instructions picker (05-06). The Playground still runs the Instructions Draft, which is the spec's Playground default. Visitors aren't served until spec 06.
- **Best guesses, recorded instead of asking:**
  - **Revert rule for Instructions.** Each Version stores the Version that was Current when it was published, and revert follows that chain. This is the spec's Live History rule ("revert sets the pointer to the from-Version of the entry that moved it onto the current Version", reading only publish entries so it doesn't toggle) without a separate log table. Every Instructions Version is published exactly once, so the two are equivalent. The revert actor and time are in the Audit log. The Agent Live History table arrives with 05-02.
  - **Nothing to publish.** A Draft identical to the Current Version, or an empty Draft before the first publish, is refused with 409. This makes concurrent publishes of one Draft produce a single Version and a clear conflict (user story 34).
  - **The note is required** (1–500 characters, trimmed). Story 2 calls it "a short note", and the ticket says "publishing takes a note".
  - **Publish in the Studio saves first.** It publishes exactly what is in the editor, so unsaved edits are never left out of a Version by surprise.
  - **Author of the migrated v1 is null** and its note says it came from the Instructions present when Versions were introduced. No real author is known.
- **Sandbox limits** (as in earlier tickets):
  - The images are built with `WITH_PDF=false BUNDLE_MODELS=false`, and the e2e stack runs `EMBEDDER=fake`, because Hugging Face is blocked here.
  - The live suite and the Trivy image scan were not run.
  - Infra checks were not run; this ticket changes no infra.
