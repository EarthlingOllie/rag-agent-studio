# 09: Deleted files are really deleted

**Ticket:** `21-09` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** When an Editor deletes a Document or replaces an edition, its stored files are removed even if the first attempt fails or the worker dies, and the work that follows a new edition is always finished.

**Blocked by:**
- `21-03`

**Status:** ready-for-agent

- [ ] A deletions table holds object keys or prefixes to delete; rows are written in the transaction that removes the last reference to them
- [ ] Deleting a Document and discarding or replacing an edition write their keys to the table instead of sending them in a message
- [ ] The sweeper deletes each entry from storage and then removes the row; an entry whose objects are already gone is removed without error
- [ ] A kill between the database commit and the storage delete leaves no orphaned object after the next sweep
- [ ] After a new edition is ingested, removing the old edition's files and refreshing Expected source Stale flags are finished by the sweeper if the worker died before doing them
- [ ] The object-deletion job no longer carries keys in its message
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
