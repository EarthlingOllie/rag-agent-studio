# 05: Dedupe, delete and replace edition

**Ticket:** `03-05` · **Spec:** [Projects and Knowledge Base](../../specs/03-projects-knowledge-base-spec.md)

**What to build:** Re-uploading an identical file is refused as a duplicate. Deleting a Document stops it being retrieved immediately. Uploading a newer edition replaces the Document in place, and the old edition keeps serving until the new one is Ready.

**Blocked by:**
- [03-02: Upload a Document to Ready](02-upload-document-to-ready.md)

**Status:** ready-for-agent

- [ ] A duplicate content hash is refused, with a link to the existing Document
- [ ] Delete removes the Chunks in the same transaction and schedules deletion of stored files, and is audited
- [ ] Replacing an edition stages new Chunks and swaps them atomically on Ready; the Document keeps its identity and Tags, and the old Chunks serve until the swap
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
