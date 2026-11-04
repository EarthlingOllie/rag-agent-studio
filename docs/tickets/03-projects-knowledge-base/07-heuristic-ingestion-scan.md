# 07: Heuristic ingestion scan

**Ticket:** `03-07` · **Spec:** [Projects and Knowledge Base](../../specs/03-projects-knowledge-base-spec.md)

**What to build:** Chunks that look like instructions aimed at an AI are flagged during ingestion, and the flags show in the Document viewer and as counts in the Document list.

**Blocked by:**
- [03-03: Document viewer](03-document-viewer.md)

**Status:** ready-for-agent

- [ ] The injection-classifier port has a heuristic adapter and a rule-driven fake
- [ ] The ingestion scan flags Chunks with a label, score and reason
- [ ] Flags appear in the viewer, and flagged-Chunk counts appear in the Document list
- [ ] End-to-end: a planted injection Chunk is flagged
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
