# 07: Retention and tombstones

**Ticket:** `07-07` · **Spec:** [Feedback, logging and comparison](../../specs/07-feedback-logging-comparison-spec.md)

**What to build:** Owners set a Retention Window. Message text and comments older than it are purged automatically while metrics stay intact. Owners can delete a single Conversation on request. Traces keep working after a Document is deleted.

**Blocked by:**
- [07-04: Rollups and Version KPIs](04-rollups-version-kpis.md)
- [03-05: Dedupe, delete and replace edition](../03-projects-knowledge-base/05-dedupe-delete-replace.md)

**Status:** ready-for-agent

- [ ] The Retention Window setting defaults to 90 days and changes are audited
- [ ] A daily purge clears Message text and comments older than the window, only after the rollups for those days are final; metrics are identical before and after
- [ ] Archived Agents and Projects are purged too
- [ ] Owners can delete a Conversation manually, which is audited
- [ ] Retrievals from a deleted Document keep its name as a tombstone, and the Trace shows it
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
