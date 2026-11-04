# 01: Projects and Project page shell

**Ticket:** `03-01` · **Spec:** [Projects and Knowledge Base](../../specs/03-projects-knowledge-base-spec.md)

**What to build:** Editors create Projects, rename and describe them, and see them listed with Document and Agent counts. Archiving hides a Project and Owners can restore it. Each Project has a page with tabs ready for Documents, Instructions, Agents, Conversations and Analytics.

**Blocked by:**
- [01-09: Member management and role enforcement](../01-skeleton-auth-tenancy/09-member-management-roles.md)

**Status:** ready-for-agent

- [ ] Projects can be created, renamed and described, and are listed with their counts
- [ ] Archiving hides a Project from the main list and stops it serving; Owners can restore it
- [ ] The Project page has tabs for Documents, Instructions, Agents, Conversations and Analytics, with placeholders where features aren't built yet
- [ ] Project-level isolation tests are added to the shared suite
- [ ] Create, archive and restore are recorded as Audit Events
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
