# 02: Upload a Document to Ready

**Ticket:** `03-02` · **Spec:** [Projects and Knowledge Base](../../specs/03-projects-knowledge-base-spec.md)

**What to build:** An Editor drops a file onto a Project and watches it go from Queued to Processing to Ready. This ticket builds the object-store port, the Celery ingestion pipeline with its converter and embedder ports, the local `multilingual-e5-small` Embedding Model, and Chunk storage with pgvector and full-text indexes.

**Blocked by:**
- [03-01: Projects and Project page shell](01-projects-shell.md)

**Status:** done

- [x] The object-store port has an S3/RustFS adapter and an in-memory fake
- [x] The upload flow is presign, then direct upload, then confirm; a SHA-256 content hash is recorded
- [x] Celery ingestion runs Docling (faked in tests), `HybridChunker` with a tokenizer matched to the Embedding Model, the local embedder, and a transactional Chunk write
- [x] Chunks store the vector, Embedding Model ID and `tsvector`, with HNSW and GIN indexes
- [x] The Document list shows live status by polling
- [x] A recorded Docling output fixture is committed, and a live-suite test runs real Docling on the sample files (closed 2026-11-06: the PDF fixture is real Docling output, the live suite passes on the real models, and the bundled-model image is built, Trivy-scanned (0 fixable HIGH or CRITICAL vulnerabilities) and e2e-tested (61 passed). Two gaps stay open: `make image-scan` still exits 1 on Trivy's secret-scanner hits in the `anthropic` SDK's docstrings, and the OCR models are not bundled because ModelScope is refused; see the evidence README's Gap closure)
- [x] End-to-end: upload the seed handbook → Ready
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
