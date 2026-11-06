# 02: Publish Agent to Live Version

**Ticket:** `05-02` · **Spec:** [Versioning and Project Instructions](../../specs/05-versioning-project-instructions-spec.md)

**What to build:** Editors publish an Agent's Draft as an immutable numbered Version that pins a Project Instructions Version and becomes the Agent's Live Version. Every Message records which Version, or the Draft, produced it.

**Blocked by:**
- [05-01: Project Instructions Versions](01-project-instructions-versions.md)
- [04-07: Full AgentConfig editor](../04-agents-retrieval-playground/07-full-agentconfig-editor.md)

**Status:** done

- [x] Publishing creates an immutable Version (config snapshot plus pinned Instructions Version, Current by default, optionally chosen) and sets the Live Version under a lock
- [x] The database refuses updates to Versions
- [x] Live History entries are written
- [x] Messages record their Agent Version, or a Draft marker in the Playground
- [x] An Agent without a Version is shown as not live
- [x] Concurrent publishes produce consecutive, unique numbers
- [x] Publishing is recorded as an Audit Event
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
