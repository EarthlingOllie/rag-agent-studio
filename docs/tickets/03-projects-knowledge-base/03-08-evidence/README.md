# Evidence: ticket 03-08, OCR toggle

Branch `ticket/03-08-ocr-toggle`, based on `origin/candidate` at `0a6a9e7` (03-02 merged). The claim commit `dba745a`, the first on the branch, set Status `in-progress`. The implementation is `22edad0`; the logs below ran on that commit with a clean worktree unless a log's first line says otherwise.

**Status: done, with one recorded gap for human review.** Every criterion is met in this sandbox except the live-model half of criterion 2: Hugging Face and ModelScope are blocked by the sandbox's egress policy (proxy `403 Forbidden`), so the live-suite test that runs real Docling with OCR on a scanned PDF is written, committed and **skips with the reason** here. That run is an explicit **GAP**, with the commands to close it below. Marking the ticket done with that gap is the recorded best guess, as the ticket brief instructs, for a human to confirm.

## What was built

- **Project OCR flag.** `projects.ocr_enabled` (Boolean, `server_default false`, migration `0012_project_ocr`). `ProjectOut.ocr_enabled`; `PATCH …/projects/{id}` takes an optional `ocr_enabled`. Archived Projects refuse the change (409), as they refuse every other change.
- **Converter port.** `DocumentConverter.convert(data, filename, *, ocr)`. Ingestion reads the Project's flag when it claims the Document and passes it on.
  - `DoclingConverter` keeps one Docling converter per setting. PDFs go through Docling's default threaded PDF pipeline with `do_ocr=ocr` and `RapidOcrOptions(backend="onnxruntime")` (`pdf_pipeline_options`). Docling's own default is OCR **on** with an auto-picked engine; before this ticket every PDF paid for OCR (and no OCR engine was installed). Other formats are unaffected.
  - The `pdf` dependency group adds `docling-slim[feat-ocr-rapidocr-onnx]` (RapidOCR on ONNX Runtime, which fastembed already brings; no extra PyTorch model). The Dockerfile's `download_models(...)` already fetches RapidOCR's models (`with_rapidocr=True` by default), so it is unchanged.
  - `FakeConverter`: a file that starts with `%SCANNED\n` stands for a scanned file. With `ocr` off its pages are empty, as Docling's are; with it on its text is read.
- **Retry.** `POST …/projects/{project_id}/documents/{document_id}/retry` (`retryDocument`, 202) sets a Ready or Failed Document back to Queued, clears its error and enqueues ingestion, which runs with the Project's **current** settings. Its current Chunks keep serving until the new ones replace them (the pipeline's final transaction swaps them). 409 for a Document still Queued or Processing, or an archived Project; 404 for an unknown Document, another Project's, or an unknown Project.
- **Studio.**
  - A **Settings** tab on the Project page (`ProjectSettingsTab.tsx`, route `…/projects/$projectId/settings`): a "Read scanned PDFs with OCR" checkbox that saves on change, help text saying OCR is slower, and a status line saying a change applies to new uploads and that Retry reprocesses an existing Document. Disabled while saving and for an archived Project; a refused save shows the API's reason.
  - The **Documents** tab: a "Retry" button on each Ready or Failed Document (none while Queued/Processing or in an archived Project). After a retry the Document shows Queued and the list polls until it is final again; a refused retry shows the API's reason.

## Seams under test

From spec 03's testing decisions and the shared test seams; no one was available to confirm them, so this is the recorded choice.
- **API seam plus task seam** (`backend/tests/integration/test_ocr.py`): Project routes, the three-step upload and retry, with ingestion running eagerly through the fake converter and the deterministic embedder. Outcomes are read through the API (Project, Document list, Chunk list), not by counting converter calls. One test arranges a Queued/Processing Document directly in the table, a state eager tasks never leave a Document in; it asserts only through the API.
- **Adapter** (`backend/tests/unit/test_docling_converter.py`): real Docling (no models) with OCR on and off on Markdown, and the PDF pipeline options it builds for each setting.
- **Live suite** (`backend/tests/live/test_docling_live.py`): real Docling with RapidOCR on a scanned PDF fixture, with OCR on and off.
- **Network seam** (`ProjectSettingsTab.test.tsx`, `DocumentsTab.test.tsx`, `ProjectPage.test.tsx`): Testing Library and MSW, handlers typed by the generated client.
- **End-to-end** (`frontend/e2e/tests/ocr.spec.ts`): Playwright with axe against the containerised stack.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | A per-Project OCR toggle exists, off by default | **API:** `ocr_enabled` on `ProjectOut`, `UpdateProjectRequest` (`app/projects/api.py`), column and migration `0012_project_ocr`. Tests: `test_a_new_project_has_ocr_off`, `test_an_editor_turns_ocr_on_and_off` (an Editor, read back by the Owner), [backend-tests.log](backend-tests.log); migration round-trip `test_migrations_upgrade_to_head_and_downgrade_to_base` in the same log.<br>**Studio:** Settings tab, `ProjectSettingsTab.test.tsx`: off by default with the slower-processing note; turn on then off (requests `{ocr_enabled: true}` then `{ocr_enabled: false}`); disabled while saving, refused change shows the reason and keeps the setting; archived Project disabled. [frontend-tests.log](frontend-tests.log).<br>**e2e:** `ocr.spec.ts`: off by default, turned on, still on after a reload, axe clean. [e2e.log](e2e.log). Screenshot: [studio-settings-ocr-on.png](studio-settings-ocr-on.png). |
| 2 | The converter receives the OCR option (tested through the fake), and a live-suite test processes a scanned PDF | **Through the fake** (`test_ocr.py`): `test_with_ocr_on_a_scanned_pdf_becomes_readable` (Ready, 1 Chunk with the scanned text), `test_with_ocr_off_a_scanned_pdf_has_no_text` (Ready, 0 Chunks), `test_ocr_doesnt_change_files_that_carry_their_own_text`. The option is observed by its effect, through the API.<br>**Adapter:** `test_docling_reads_pdfs_with_ocr_only_when_asked` (`do_ocr` per setting, RapidOCR on ONNX Runtime), `test_ocr_doesnt_change_formats_that_carry_their_own_text[False/True]` (real Docling).<br>**Live suite:** `test_real_docling_reads_a_scanned_pdf_only_with_ocr` converts `tests/fixtures/documents/scanned-leave-policy.pdf` (one A4 page that is only an image of text, no text layer; written by `make_sample_documents.write_scanned_pdf`, preview [scanned-leave-policy.png](scanned-leave-policy.png)) with OCR on (expects "25 days" and "annual leave", and a Chunk with them) and off (expects no "25 days"). **GAP:** it skips here with the reason, [live-suite.log](live-suite.log), and fails as intended under `LIVE_REQUIRE_MODELS=1`, [live-suite-require-models.log](live-suite-require-models.log). See Gaps. |
| 3 | Existing Documents can be reprocessed with the new setting through retry | **API** (`test_ocr.py`): `test_retry_reprocesses_a_document_with_ocr_turned_on` (uploaded with OCR off: 0 Chunks; OCR on, retry: 202 Queued, then Ready with the scanned text, same Document ID), `test_retry_with_ocr_turned_off_drops_the_text_ocr_read` (old Chunks still counted while Queued, gone after), `test_retry_reprocesses_a_failed_document`, `test_a_document_still_being_processed_cant_be_retried[queued/processing]` (409 with reason), `test_an_archived_projects_documents_cant_be_retried` (409), `test_retrying_an_unknown_document_or_anothers_projects_is_not_found` (404 ×3).<br>**Studio** (`DocumentsTab.test.tsx`): Retry on Ready and Failed rows, Failed → Queued → Ready with the error cleared and polling; no Retry while Processing or in an archived Project; refused retry shows the reason (button disabled while pending); a reasonless failure asks to try again.<br>**e2e:** `ocr.spec.ts` retries the uploaded handbook after turning OCR on; it is Ready again with Chunks, axe clean. Screenshot: [studio-documents-retry.png](studio-documents-retry.png). |
| 4 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | [backend-tests.log](backend-tests.log): `make test-backend`, 100% line and branch (see its `TOTAL` line). [frontend-tests.log](frontend-tests.log): `make test-frontend`, 100% statements, branches, functions and lines. [lint.log](lint.log): `make lint` (ruff, ruff format, `mypy --strict`, eslint, `tsc`). [client-drift.log](client-drift.log): `make check-client` up to date. [e2e.log](e2e.log): `make e2e`. Seams as listed above. |
| 5 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md` (Knowledge) gains **OCR** (per-Project setting, off by default, slower, applies to Documents processed afterwards) and **Retry** (a Ready or Failed Document through ingestion again with current settings; its Chunks serve until replaced). No ADR changed: the spec already decided OCR is a per-Project flag; Docling stays faked at the one converter seam (ADR-0008) and its adapter stays inside the coverage gate. |

## Decisions and notes (best guesses recorded instead of asking)

- **Retry overlaps ticket 03-04**, which also lists "Editors can retry a failed Document" (with categories and automatic backoff). This ticket needs retry to reprocess existing Documents, so it adds the manual retry endpoint and button; 03-04 can build its categories and automatic retries on it. Unlike a failure-only retry, this one also accepts **Ready** Documents, since a scanned PDF processed without OCR is Ready with no text, not Failed.
- **A Document processed without OCR stays Ready with 0 Chunks** (what the pipeline already does with an empty conversion). Whether an empty conversion should Fail as "unsupported content" is 03-04's categorisation.
- **A retry that fails keeps the previous Chunks** (the pipeline only replaces Chunks in its final transaction), so a transient failure doesn't empty the Knowledge Base; the status shows Failed with the reason.
- **OCR engine:** RapidOCR on ONNX Runtime, not EasyOCR (PyTorch, larger) or Tesseract (system package). Language: RapidOCR's default.
- **Settings tab.** The spec's "Project settings" area didn't exist yet; it is added as a sixth Project tab holding only OCR. 03-09/03-10 (Embedding Model) and 03-04 (quota display) can add to it.
- **No audit event** for the OCR change: spec 03's audited changes list doesn't include it.
- **Migration number** `0012_project_ocr` follows candidate's head `0011_documents`; a parallel ticket's `0012` merged first would need this one's `down_revision` re-pointed.
- **Converter signature.** `ocr` is a required keyword, so a converter that ignores it fails `mypy`. A parallel branch adding its own converter or `convert(...)` call needs `ocr=`.

## Gaps and sandbox notes

- **GAP (criterion 2, live half): no live OCR run.** huggingface.co (Docling's layout model) and www.modelscope.cn (RapidOCR's models) answer `403 Forbidden` through the sandbox's egress proxy. The live test is committed and skips with the reason. **To close it**, on a machine that can reach both, from a checkout of the branch:
  1. `make install`
  2. `LIVE_REQUIRE_MODELS=1 make test-live`: expect `test_real_docling_reads_a_scanned_pdf_only_with_ocr` to pass (with the other live tests: 6 passed, 0 skipped). If RapidOCR reads the rendered text slightly differently, adjust only the substrings asserted.
  3. Optionally, `IMAGE_TAG=pdf make image-scan` and `make e2e` with the default `WITH_PDF=true BUNDLE_MODELS=true` images, then upload `backend/tests/fixtures/documents/scanned-leave-policy.pdf` to a Project with OCR off (Ready, 0 Chunks), turn OCR on in Settings and Retry it (Ready, Chunks with "25 days of annual leave").
- **Images were built without PDF support and models** (`WITH_PDF=false BUNDLE_MODELS=false`, [build.sh](build.sh), [images.log](images.log)), as for 03-02: the models can't be downloaded and the disk is shared. So the e2e stack runs real Docling on Markdown (no models) with `EMBEDDER=fake`; OCR on Markdown is a no-op, so e2e proves the toggle and retry wiring, not OCR itself. `uv.lock` was re-locked with RapidOCR; the `pdf` group installed and the live test imported and skipped ([live-suite.log](live-suite.log)).
- **Host load.** Eight tickets share this machine (load average ~40). The first e2e attempt failed because the API's health check ran out of retries before it finished starting ([e2e-attempt1-api-slow-start.log](e2e-attempt1-api-slow-start.log)); the stack was left up and the suite re-run.
- **No real cloud, email or paid APIs.**

## Files

| File | What it is |
|---|---|
| `backend-tests.log`, `frontend-tests.log`, `lint.log`, `client-drift.log` | `make test-backend`, `make test-frontend`, `make lint`, `make check-client` |
| `live-suite.log`, `live-suite-require-models.log` | `make test-live` (skips with reasons), and with `LIVE_REQUIRE_MODELS=1` (fails on the missing models) |
| `images.log`, `build.sh` | The two image builds with the sandbox CA |
| `e2e.log`, `e2e.env`, `compose.sandbox.yml`, `e2e-attempt1-api-slow-start.log` | `make e2e` on the containerised stack, its environment and port/image override, and the first attempt |
| `scanned-leave-policy.png` | The scanned PDF fixture's page, rendered |
| `studio-*.png`, `shots.mjs` | Screenshots of the Settings tab and the Documents tab with Retry, from the e2e stack |
