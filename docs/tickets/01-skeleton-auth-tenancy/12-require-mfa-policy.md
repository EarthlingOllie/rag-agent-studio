# 12: Require MFA policy

**Ticket:** `01-12` · **Spec:** [Skeleton, CI, auth and tenancy](../../specs/01-skeleton-auth-tenancy-spec.md)

**What to build:** An Owner can require MFA for everyone in the Organisation. Members without MFA are guided through enrolment before they can do anything else in that Organisation.

**Blocked by:**
- [01-09: Member management and role enforcement](09-member-management-roles.md)
- [01-11: TOTP MFA](11-totp-mfa.md)

**Status:** ready-for-agent

- [ ] The Owner toggle is in Organisation settings
- [ ] Members without MFA are redirected to enrolment, and the API refuses that Organisation's routes until they enrol
- [ ] A Member can't disable MFA while any of their Organisations requires it
- [ ] Policy changes are recorded as Audit Events
- [ ] End-to-end: an Owner requires MFA → an Editor is forced to enrol on their next visit
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
