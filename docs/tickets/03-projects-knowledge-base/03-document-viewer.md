# 03: Document viewer

**Ticket:** `03-03` · **Spec:** [Projects and Knowledge Base](../../specs/03-projects-knowledge-base-spec.md)

**What to build:** An Editor opens a Document and sees Docling's converted markdown next to its Chunks, with heading context and page numbers, so they know exactly what an Agent can retrieve. They can also download the original file.

**Blocked by:**
- [03-02: Upload a Document to Ready](02-upload-document-to-ready.md)

**Status:** done

- [x] Rendered markdown appears beside the Chunk list, with each Chunk's heading path and page range
- [x] The original file downloads through a presigned GET
- [x] The Chunk list paginates for large Documents
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
