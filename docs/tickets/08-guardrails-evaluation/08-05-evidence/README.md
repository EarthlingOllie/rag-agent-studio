# Evidence: ticket 08-05, Classifier-based ingestion scan

Branch `ticket/08-05-classifier-ingestion-scan`, from `origin/candidate` at `a2e4a26` (all three blockers merged and `done`: 08-01 Input Guardrail, 03-07 Heuristic ingestion scan, 04-03 Hybrid retrieval). The claim commit `cb186e5`, the first on the branch, set Status `in-progress`.

**Status: done.** Every criterion is met and evidenced below. Gaps and judgement calls are listed at the end.

## What was built

- **Ingestion uses the local classifier** (`backend/app/documents/ports.py`): `INJECTION_CLASSIFIER=local|heuristic|fake`, default now `local` (was `heuristic`), with `INJECTION_CLASSIFIER_THRESHOLD` (default 0.5, as the input Guardrail). The ingestion port builds a `LocalClassifier(onnx_model.load, threshold, subject="Chunk")`, so a flag's reason reads "The local classifier scored the Chunk 1.00 as a prompt injection." `onnx_model.load` is now `functools.cache`d, so the API (input Guardrail + eager ingestion) and the worker each hold **one** copy of the model. `docker-compose.yml` passes `INJECTION_CLASSIFIER` (default `local`); the model is already bundled in the API/worker image (`BUNDLE_MODELS=true`, ticket 08-01). The heuristic adapter stays for stacks built without the model.
- **Flagged Chunk mode** (per Project): `projects.flagged_chunk_mode` (`mark` | `exclude`, default `mark`, check constraint; migration `0032_flagged_chunk_mode`, reversible). `ProjectOut.flagged_chunk_mode`; `PATCH /projects/{id}` accepts it (422 for any other value, 409 for an archived Project).
- **Retrieval honours exclude** (`backend/app/retrieval/service.py`): with `exclude`, Chunks carrying a Guardrail flag are taken out of the ranking **before** the reranker, the minimum score and `top_k`, so they are never candidates, take no candidate place, and are never sent to a provider reranker. They are returned as `Excluded(reason="guardrail_flagged")`, which the Playground/widget save as Message retrievals, so the **Trace** lists them. With `mark`, nothing changes.
- **Clearing a flag** (`DELETE /api/organisations/{org}/projects/{project}/documents/{document}/chunks/{chunk}/flag`, operation `clearChunkFlag`, `Scope` = any Editor or Owner): clears the flag on a Chunk of the Document's current edition, on every Embedding Model's copy (a re-embed in progress keeps one per model), and records the Audit Event `chunk.flag_cleared` (target `chunk`, `before` = project, document, label, score, reason; `after` = `{"flag": null}`) in the same transaction. 404 for a Chunk not in that Document's current edition / another Project / another Organisation; 409 "This Chunk isn't flagged."; 409 for an archived Project.
- **Studio**: Project Settings tab gains a "Flagged Chunks" radio group (Mark them, and keep retrieving them / Exclude them from retrieval) with a status sentence; each flagged Chunk in the Document viewer has a "Clear flag" button (accessible name "Clear flag on Chunk N"), showing the API's refusal if any; the Trace drawer labels the new reason "Excluded: flagged by the ingestion scan". API client regenerated.
- Docs: `GLOSSARY.md` (new **Flagged Chunk mode**; **Ingestion scan**, **Injection classifier**, **Guardrail flag**, **Local classifier** updated), ADR-0007 (a paragraph on the scan's classifier, mark vs exclude, and clearing), `docs/development.md`.

## Test seams

The [shared test seams](../../../specs/README.md#shared-test-seams), as spec 08's Testing Decisions name them ("Ingestion: with the exclude setting, a flagged Chunk never appears in retrieval candidates; clearing a flag restores it and is audited"; "Frontend, network seam: … Chunk flag clearing"). No human was available to confirm seams; these are the pre-agreed ones.

- **API seam** (`backend/tests/integration/test_flagged_chunks.py`): the in-process API with real Postgres/pgvector and Redis, the rule-driven fake classifier, the fixture Knowledge Base and a recording `FunctionModel`; assertions on the Project, the Chunks, the Document list, the Playground **Trace** and the Audit Events, all read through the API.
- **Unit** (`tests/unit/test_ingestion_ports.py`, `tests/unit/test_local_injection_classifier.py`): the settings choose the scan's adapter and threshold; the reason names what was classified.
- **Live suite** (`tests/live/test_ingestion_scan_live.py`): the real ONNX model, built from the settings as production builds it, on the seed's Markdown Documents.
- **Network seam** (`ProjectSettingsTab.test.tsx`, `DocumentViewer.test.tsx`, `AgentPage.test.tsx`) with MSW.
- **End-to-end** (`frontend/e2e/tests/documents.spec.ts`): the compose stack with the real bundled model in the worker.

## Acceptance criteria

RESULTS_TABLE

## Gaps and judgement calls

- **Default mode is `mark`.** The spec lets each Project choose but names no default; `mark` keeps 03-07's behaviour for existing Projects and avoids a false positive silently hiding content. Changing the mode is not itself audited (only clearing a flag is, as the ticket asks); it is a plain Project setting like OCR.
- **A cleared flag lasts until the Document is next scanned.** Retrying or replacing the Document re-runs the scan, which may flag the Chunk again; the Audit Event keeps the history. There is no "never flag this text again" allow-list (not asked for).
- **No ingestion-time threshold per Project**; one setting (`INJECTION_CLASSIFIER_THRESHOLD`) per deployment.
- Trace rows for `guardrail_flagged` Chunks are capped by what retrieval found (the 50-per-search candidate pool), as for every other exclusion reason.
- Infra (terraform) is unchanged: the deployed API/worker take the new default from settings and already run the image that bundles the model.
- GitHub Actions is down; all checks ran locally, one at a time (the user authorised merging on local results).
