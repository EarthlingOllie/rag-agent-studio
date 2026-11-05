# 06: Tags

**Ticket:** `03-06` · **Spec:** [Projects and Knowledge Base](../../specs/03-projects-knowledge-base-spec.md)

**What to build:** Editors organise Documents with Tags, applied one at a time or in bulk, and filter the Document list by name, status and Tag.

**Blocked by:**
- [03-02: Upload a Document to Ready](02-upload-document-to-ready.md)

**Status:** done

- [x] Tags can be created, renamed and deleted per Project
- [x] Several Tags can be applied to a Document, and Tags can be bulk-applied to many Documents
- [x] The Document list filters and searches by name, status and Tag
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
