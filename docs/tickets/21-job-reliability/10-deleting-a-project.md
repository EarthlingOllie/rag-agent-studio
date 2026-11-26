# 10: Deleting a Project

**Ticket:** `21-10` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** An Owner who deletes an archived Project sees it as Deleting at once; it can't be used or restored, and its rows and files always go, even if the first attempt is lost.

**Blocked by:**
- `21-09`

**Status:** ready-for-agent

- [ ] The delete request records a deleting mark and who asked, in the request's transaction, and returns as it does today
- [ ] A Deleting Project is left out of Project lists and pickers, and refuses uploads, edits, restoring and Visitor messages with a clear reason
- [ ] The cascade deletes the Project's rows and writes its storage prefix to the deletions table in one transaction; the sweeper removes the files
- [ ] A deletion whose message was lost, or whose worker died at any point, is finished by the sweeper
- [ ] Running the deletion twice, or as two copies at once, is harmless
- [ ] The archived Projects view shows Deleting until the Project is gone, and the confirmation says a deleted Project can't be restored
- [ ] Only Owners can delete; another Organisation's Project is unreachable
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
