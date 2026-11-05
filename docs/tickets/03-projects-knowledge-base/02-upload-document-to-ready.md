# 02: Upload a Document to Ready

**Ticket:** `03-02` · **Spec:** [Projects and Knowledge Base](../../specs/03-projects-knowledge-base-spec.md)

**What to build:** An Editor drops a file onto a Project and watches it go from Queued to Processing to Ready. This ticket builds the object-store port, the Celery ingestion pipeline with its converter and embedder ports, the local `multilingual-e5-small` Embedding Model, and Chunk storage with pgvector and full-text indexes.

**Blocked by:**
- [03-01: Projects and Project page shell](01-projects-shell.md)

**Status:** in-progress

- [ ] The object-store port has an S3/RustFS adapter and an in-memory fake
- [ ] The upload flow is presign, then direct upload, then confirm; a SHA-256 content hash is recorded
- [ ] Celery ingestion runs Docling (faked in tests), `HybridChunker` with a tokenizer matched to the Embedding Model, the local embedder, and a transactional Chunk write
- [ ] Chunks store the vector, Embedding Model ID and `tsvector`, with HNSW and GIN indexes
- [ ] The Document list shows live status by polling
- [ ] A recorded Docling output fixture is committed, and a live-suite test runs real Docling on the sample files
- [ ] End-to-end: upload the seed handbook → Ready
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
