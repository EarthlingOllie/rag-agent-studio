# 09: Member management and role enforcement

**Ticket:** `01-09` · **Spec:** [Skeleton, CI, auth and tenancy](../../specs/01-skeleton-auth-tenancy-spec.md)

**What to build:** Owners see every Member with their role, change roles between Owner and Editor, and remove Members. Members can leave. The Organisation can never lose its last Owner, and Owner-only areas are refused by the API and hidden in the UI for Editors.

**Blocked by:**
- [01-08: Invites and joining an Organisation](08-invites-joining.md)

**Status:** ready-for-agent

- [ ] The Members list shows each Member's role
- [ ] Owners can change roles and remove Members, and any Member can leave
- [ ] Demoting, removing or leaving as the last Owner is refused
- [ ] One policy dependency declares the required role per route; Editors get 403 from Owner-only routes and don't see Owner-only navigation
- [ ] Removing a Member revokes their access to that Organisation immediately
- [ ] Every change is recorded as an Audit Event
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
