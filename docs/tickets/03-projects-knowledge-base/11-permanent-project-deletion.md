# 11: Permanent Project deletion

**Ticket:** `03-11` · **Spec:** [Projects and Knowledge Base](../../specs/03-projects-knowledge-base-spec.md)

**What to build:** Owners can permanently delete an archived Project after typing its name. Everything inside it is removed, including stored files.

**Blocked by:**
- [03-05: Dedupe, delete and replace edition](05-dedupe-delete-replace.md)

**Status:** done

- [x] Only Owners can do it, only for archived Projects, and only after typing the name
- [x] A Celery cascade removes Documents, Chunks and stored files, and later Agents and Conversations
- [x] Deletion is recorded as an Audit Event
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
