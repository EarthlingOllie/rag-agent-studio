# 10: Organisation switcher

**Ticket:** `01-10` · **Spec:** [Skeleton, CI, auth and tenancy](../../specs/01-skeleton-auth-tenancy-spec.md)

**What to build:** A Member who belongs to several Organisations can switch between them without signing out, and nothing leaks between them.

**Blocked by:**
- [01-08: Invites and joining an Organisation](08-invites-joining.md)

**Status:** done

- [x] Members with several memberships see a switcher, and their choice persists across reloads
- [x] Organisation-scoped routes carry the active Organisation, and switching never shows another Organisation's data
- [x] Isolation tests cover a Member who belongs to two Organisations
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
