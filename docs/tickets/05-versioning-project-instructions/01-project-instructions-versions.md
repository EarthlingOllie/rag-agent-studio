# 01: Project Instructions Versions

**Ticket:** `05-01` · **Spec:** [Versioning and Project Instructions](../../specs/05-versioning-project-instructions-spec.md)

**What to build:** Project Instructions get a Draft, immutable numbered Versions and a Current Version. Editors publish with a note, browse the history, and revert the Current Version.

**Blocked by:**
- [04-02: Markdown editor](../04-agents-retrieval-playground/02-markdown-editor.md)

**Status:** ready-for-agent

- [ ] Instructions have a Draft, immutable numbered Versions and a Current Version pointer
- [ ] A migration turns the existing Instructions field into the Draft plus a v1, and the data is asserted
- [ ] Publishing takes a note; the history is listed; revert moves the Current Version back
- [ ] Publish and revert are recorded as Audit Events
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
