# 03: Revert via Live History

**Ticket:** `05-03` · **Spec:** [Versioning and Project Instructions](../../specs/05-versioning-project-instructions-spec.md)

**What to build:** Editors revert an Agent to the Version that was previously Live. That restores both its config and the Instructions it was pinned to, following the Live History rather than version numbers.

**Blocked by:**
- [05-02: Publish Agent to Live Version](02-publish-agent-live-version.md)

**Status:** done

- [x] Revert follows the Live History, verified by a table-driven test of action sequences including publish → revert → revert
- [x] Revert is refused when there's nothing to revert to
- [x] Revert restores both config and pinned Instructions (verified with an echoing `FunctionModel`)
- [x] A Live History timeline is shown in the UI, and reverts are audited
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
