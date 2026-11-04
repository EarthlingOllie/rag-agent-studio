# 08: OCR toggle

**Ticket:** `03-08` · **Spec:** [Projects and Knowledge Base](../../specs/03-projects-knowledge-base-spec.md)

**What to build:** Editors can turn on OCR for a Project so scanned PDFs become readable, without slowing down Projects that don't need it.

**Blocked by:**
- [03-02: Upload a Document to Ready](02-upload-document-to-ready.md)

**Status:** ready-for-agent

- [ ] A per-Project OCR toggle exists, off by default
- [ ] The converter receives the OCR option (tested through the fake), and a live-suite test processes a scanned PDF
- [ ] Existing Documents can be reprocessed with the new setting through retry
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
