# 04: Diffs and Draft management

**Ticket:** `05-04` · **Spec:** [Versioning and Project Instructions](../../specs/05-versioning-project-instructions-spec.md)

**What to build:** Editors see exactly what changed between any two Versions, or between the Draft and the Live Version. They can discard a Draft, start a new Draft from any past Version, and never silently overwrite a colleague's edits.

**Blocked by:**
- [05-02: Publish Agent to Live Version](02-publish-agent-live-version.md)

**Status:** done

- [x] A structural AgentConfig diff with text diffs for markdown covers Version-to-Version and Draft-to-Live
- [x] An unpublished-changes badge is shown
- [x] Editors can discard the Draft, or start a Draft from any Version
- [x] Saving a stale Draft returns 409 with the latest Draft, and the UI prompts to resolve the conflict
- [x] The publish dialog shows the Draft-to-Live diff
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
