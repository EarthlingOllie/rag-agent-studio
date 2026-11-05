# Evidence: ticket 03-06, Tags

Branch `ticket/03-06-tags`, based on `origin/candidate` at `0a6a9e7` (03-02 merged). The claim commit `97a2004`, the first on the branch, set Status `in-progress`. The feature is commit `028db9e`; this README and the Status change follow it.

**Status: done.** Every acceptance criterion is met and evidenced below. Gaps and judgement calls are listed at the end.

## What was built

- **Backend** (`backend/app/tags/`, new module):
  - `models.py`: `Tag` (Organisation, Project, name; unique per Project ignoring case through the index `uq_tags_project_name` on `(project_id, lower(name))`) and `DocumentTag` (the many-to-many link, carrying the Organisation like every non-platform table; deleting a Document or a Tag removes the link by `ON DELETE CASCADE`).
  - `service.py`: list (with each Tag's Document count), create, rename, delete, set one Document's Tags, bulk add/remove on many Documents. Everything finds the Project inside the caller's Organisation; changes go through `active_project`, so an archived Project's Tags are read-only. A Tag or Document ID from another Project is "not in this Project".
  - `api.py`: the routes below. Any Member (Editor or Owner) may use them, as with Documents.
  - `migrations/versions/20261105_0012_tags.py`: `tags` and `document_tags`, revising `0011_documents`.
  - `app/documents/`: `DocumentOut` gains `tags` (id and name, by name). `GET …/documents` gains `q` (part of the name, ignoring case; `%` and `_` are literal), `status` (repeatable: any of) and `tag_id` (repeatable: all of).
- **Studio** (`frontend/apps/studio/src/projects/`):
  - `TagsPanel.tsx` + `tags.ts`: the Tags region on the Documents tab: each Tag with its Document count, Rename (inline), Delete (with a confirmation naming how many Documents it leaves), and New Tag. The API's reasons (duplicate name, archived Project) are shown.
  - `DocumentsTab.tsx`: a Tags column; "Edit Tags" on each row opens a checkbox group to choose exactly which Tags the Document carries; row checkboxes and Select all open the Bulk tagging bar (choose a Tag, Apply to selected / Remove from selected / Clear selection); a search box and Status and Tag filters, sent to the API, with Clear filters and a "No Documents match these filters." empty state. In an archived Project the Tags and filters show but nothing can be changed.
  - `documents.ts`: `useDocuments` takes the filters and keeps the previous list up while a new filter loads.
  - The generated API client is regenerated (`make gen-client`).

| Route | Purpose |
|---|---|
| `GET /api/organisations/{org}/projects/{project}/tags` | The Project's Tags by name, with `document_count` |
| `POST …/tags` `{name}` | Create; 409 for a duplicate name (ignoring case) or an archived Project |
| `PATCH …/tags/{tag}` `{name}` | Rename; Documents keep the Tag |
| `DELETE …/tags/{tag}` | Delete; it is taken off every Document, which stay |
| `PUT …/documents/{document}/tags` `{tag_ids}` | Set exactly the Document's Tags (several, or none) |
| `POST …/documents/tags` `{document_ids, add, remove}` | Bulk-apply and/or remove Tags on up to 500 Documents at once |
| `GET …/documents?q=&status=&tag_id=` | Search and filter the Document list |

**Seams under test.** From spec 03's testing decisions and the shared test seams. There was no one to confirm them with, so this is the recorded choice: the **API seam** (`tests/integration/test_tags.py`, plus the parametrised isolation suite), the **network seam** (`DocumentTags.test.tsx`, Testing Library + MSW with a stateful fake typed by the generated client), and the **end-to-end seam** (`e2e/tests/tags.spec.ts`, Playwright + axe on the containerised stack). Nothing reads tables directly.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Tags can be created, renamed and deleted per Project | **API tests** (`backend/tests/integration/test_tags.py`):<br>• `test_an_editor_creates_tags_listed_by_name`: an Editor creates three Tags (whitespace trimmed); listed case-insensitively by name with `document_count` 0.<br>• `test_tag_names_are_unique_in_a_project_ignoring_case`: `hr` after `HR` is 409 "This Project already has a Tag with that name."; the same name in another Project is fine.<br>• `test_a_blank_or_overlong_tag_name_is_refused`: blank and 51-character names are 422.<br>• `test_an_editor_renames_a_tag_and_documents_keep_it`: rename, re-case its own name, and a rename onto another Tag's name is 409; the Document shows the new name.<br>• `test_deleting_a_tag_takes_it_off_documents_which_stay`: 204, then 404; the Document stays with its other Tag.<br>• `test_an_unknown_tag_cannot_be_renamed`: another Project's Tag is 404 through this Project.<br>• `test_an_archived_projects_tags_can_be_read_but_not_changed`: create, rename, delete, set and bulk all 409 with the archived message; the list still reads.<br>• Isolation suite (`test_tenant_isolation.py`): the six new routes are added to `PROJECT_SCOPED_ROUTES`, so each is checked for another tenant (404 indistinguishable from a missing Organisation), signed-out (401), Editors allowed, a Member of two Organisations, and a Project found only through its own Organisation ([isolation-tests.log](isolation-tests.log)).<br>**Studio tests** (`DocumentTags.test.tsx`): create (trimmed, cleared after, listed by name with counts), blank and duplicate refusals, rename (and Documents show the new name), rename refusal and Cancel, delete with confirmation and "Keep it", failures without a reason say "Something went wrong. Try again.", the Tags failing to load, and an archived Project's Tags read-only.<br>**e2e** (`tags.spec.ts`): creates HR, Policy and Sales, a duplicate `hr` is refused, renames HR to People, deletes Policy. |
| 2 | Several Tags can be applied to a Document, and Tags can be bulk-applied to many Documents | **API tests:**<br>• `test_several_tags_are_applied_to_a_document_and_can_be_cleared`: set two Tags, then a different two (one dropped), counts per Tag, then clear with `[]`.<br>• `test_a_tag_from_another_project_cannot_be_applied`: another Project's Tag is 422 "One or more of these Tags aren't in this Project."; another Project's Document is 404; nothing changes.<br>• `test_tags_are_bulk_applied_to_and_removed_from_many_documents`: `add` to two of three Documents (one already had a Tag: no duplicate), then `add` + `remove` in one request on another pair; counts follow.<br>• `test_bulk_tagging_refuses_documents_or_tags_outside_the_project`: foreign Document, foreign Tag in `add` or `remove`, and an empty `document_ids` are 422 and change nothing.<br>**Studio tests:** "an Editor applies several Tags to one Document" (checkbox group, PUT body `{tag_ids: [HR, Policy]}`), cancel and a refusal's reason, the no-Tags-yet hint, "an Editor bulk-applies a Tag to many Documents and takes it off again" (exact request bodies), and "select all picks every listed Document, and a bulk refusal shows its reason".<br>**e2e:** two Tags on `leave-policy.md` through Edit Tags, then HR bulk-applied to two Documents; the Tags panel shows "2 Documents"; axe finds no violations with the bulk bar open. |
| 3 | The Document list filters and searches by name, status and Tag | **API tests:**<br>• `test_the_document_list_filters_by_name_status_and_tag`: four Documents (one Failed through the fake converter): `q` ignores case and surrounding spaces, `%` and `_` match literally, `status` any-of, `tag_id` all-of, and all three combined; a combination matching nothing is `[]`.<br>• `test_an_unknown_status_filter_is_refused`: 422.<br>**Studio test** "the Document list is searched by name and filtered by status and Tag": the query string sent is `q=e&status=ready&tag_id=…`, "No Documents match these filters.", and Clear filters resets the search box and the list.<br>**e2e:** filter by the People Tag, then search `LEAVE`, then Status Failed (empty state), then Clear filters shows all three. |
| 4 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | See **Checks** below: backend 100% line and branch, frontend 100% lines, branches, functions and statements, and the e2e suite. |
| 5 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md` **Tag** now says a Tag belongs to one Project with a name unique there ignoring case, a Document can carry several, Editors apply them one Document at a time or in bulk, and what renaming and deleting do. No new terms otherwise ("bulk tagging" is described under Tag). No ADR decision changed: Tags follow ADR-0001 (every row carries `organisation_id` and `project_id` filtering). |

## Checks

Run from this worktree at the feature head (`63d112a` plus this evidence), one suite at a time, against a compose project `rag0306` started with `compose.sandbox.yml` (ports moved so it runs beside other tickets' stacks).

| Check | Command | Result | Log |
|---|---|---|---|
| Backend lint + types | `make lint` (ruff check, ruff format --check, mypy --strict; eslint, tsc) | pass | [lint.log](lint.log) |
| Backend tests | `uv run pytest` with `TEST_DATABASE_URL`, `TEST_REDIS_URL`, `TEST_OBJECT_STORE_URL` pointing at `rag0306` (includes the Alembic up/down round-trip) | 875 passed, 5 deselected (`live`); **100% line and branch** (4438 statements, 420 branches) | [backend-tests.log](backend-tests.log) |
| Tags API tests (verbose) | `pytest -v tests/integration/test_tags.py` | 13 passed | [tags-api-tests.log](tags-api-tests.log) |
| Isolation suite, Tag routes (verbose) | `pytest -v tests/integration/test_tenant_isolation.py -k tag` | 42 passed | [isolation-tests.log](isolation-tests.log) |
| Frontend tests | `make test-frontend` (`vitest run --coverage`) | 29 files, 308 tests passed; **100%** statements, branches, functions and lines | [frontend-tests.log](frontend-tests.log) |
| API client drift | `make check-client` | "API client is up to date." | [client-drift.log](client-drift.log) |
| End-to-end | `build.sh` images, then `docker compose -p rag0306 -f docker-compose.yml -f compose.sandbox.yml up -d --wait` and `pnpm e2e --workers=1` with [e2e.env](e2e.env) | 43 passed, including `tags.spec.ts` (with axe) | [stack-up.log](stack-up.log), [e2e.log](e2e.log) |
| Secret scan | `gitleaks git --log-opts=HEAD` and `gitleaks dir` on this folder | no leaks | [secret-scan.log](secret-scan.log) |

No dependency or lockfile changed on this branch, so `make audit` and the Trivy image scan are unchanged from candidate and were not re-run.

## Gaps and judgement calls

- **Seams were not confirmed with a human** (none available); the choice is recorded above.
- **Machine load.** Four tickets build in parallel on this 4-CPU host. The e2e run uses one Playwright worker so slow pages don't hit timeouts; no test or timeout was changed.
- **e2e images.** Built by `build.sh` (the committed Dockerfiles plus this sandbox's egress CA) with `WITH_PDF=false BUNDLE_MODELS=false` and the fake embedder: Hugging Face is blocked here and the disk is small. The images were built after the feature commit `028db9e`; the commits since change only test files. GitHub Actions is down, so these local runs are the record.
- **Secret scan scope.** `make secret-scan` scans every ref in the shared clone and reports one finding in commit `a7613be` on `ticket/03-09-provider-embedding-models` (another ticket's branch, not on this one). Scoped to this branch's history it is clean; that ticket allowlists its own fixture.
- **Bulk semantics.** A Tag in both `add` and `remove` is removed (documented in the API schema). Bulk requests are capped at 500 Documents and 100 Tags per list. A tag name is at most 50 characters. These limits are my choice; the spec sets none.
- **Filter semantics.** Several `status` values match any of them; several `tag_id` values match Documents that carry all of them (the Studio sends at most one of each). The status poll (`/documents/statuses`) is not filtered; it only updates rows already listed.
- **Audit Events.** Spec 03 lists the audited Knowledge Base actions (Project lifecycle, Embedding Model changes, Document deletes); Tag changes are not among them, so none are recorded.
- **Migration number.** `0012_tags` revises `0011_documents`. Tickets 03-03, 03-04, 03-05 and 03-08 are building in parallel and may add their own `0012`; whichever merges second re-parents its migration, as 03-02 did.
