# 05: Audit Events and Audit tab

**Ticket:** `01-05` · **Spec:** [Skeleton, CI, auth and tenancy](../../specs/01-skeleton-auth-tenancy-spec.md)

**What to build:** Any security- or configuration-relevant change can be recorded as an Audit Event through one audit operation, and Owners can browse and filter Audit Events in an Audit tab. Creating an Organisation is the first event recorded.

**Blocked by:**
- [01-04: Sign up, sign in, sign out](04-sign-up-sign-in-sign-out.md)

**Status:** ready-for-agent

- [ ] The audit record operation stores actor, Organisation, action, target, before/after values and time in an append-only table
- [ ] Secret-like fields are redacted before storage
- [ ] An Owner-only list endpoint supports filtering by actor, action and date range, with pagination
- [ ] The Audit tab in Organisation settings is hidden from Editors, and the API refuses them
- [ ] Organisation creation at sign-up is recorded
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
