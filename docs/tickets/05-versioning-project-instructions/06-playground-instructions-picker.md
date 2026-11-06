# 06: Playground Instructions picker

**Ticket:** `05-06` · **Spec:** [Versioning and Project Instructions](../../specs/05-versioning-project-instructions-spec.md)

**What to build:** Editors test an Agent's Draft in the Playground against the Instructions Draft or any Instructions Version, before publishing either.

**Blocked by:**
- [05-01: Project Instructions Versions](01-project-instructions-versions.md)

**Status:** done

- [x] The picker offers the Instructions Draft (the default) or any Version
- [x] Playground Messages record the Instructions Version or a Draft marker
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
