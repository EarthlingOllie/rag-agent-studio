# 09: Member management and role enforcement

**Ticket:** `01-09` · **Spec:** [Skeleton, CI, auth and tenancy](../../specs/01-skeleton-auth-tenancy-spec.md)

**What to build:** Owners see every Member with their role, change roles between Owner and Editor, and remove Members. Members can leave. The Organisation can never lose its last Owner, and Owner-only areas are refused by the API and hidden in the UI for Editors.

**Blocked by:**
- [01-08: Invites and joining an Organisation](08-invites-joining.md)

**Status:** done

- [x] The Members list shows each Member's role
- [x] Owners can change roles and remove Members, and any Member can leave
- [x] Demoting, removing or leaving as the last Owner is refused
- [x] One policy dependency declares the required role per route; Editors get 403 from Owner-only routes and don't see Owner-only navigation
- [x] Removing a Member revokes their access to that Organisation immediately
- [x] Every change is recorded as an Audit Event
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
