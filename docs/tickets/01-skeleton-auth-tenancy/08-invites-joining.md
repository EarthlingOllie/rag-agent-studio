# 08: Invites and joining an Organisation

**Ticket:** `01-08` · **Spec:** [Skeleton, CI, auth and tenancy](../../specs/01-skeleton-auth-tenancy-spec.md)

**What to build:** Owners invite colleagues by email, or with a copyable link, with a chosen role. A person without an account creates one and joins in a single flow; an existing Member just gains the new membership.

**Blocked by:**
- [01-05: Audit Events and Audit tab](05-audit-events.md)
- [01-07: Mailer, password reset and change password](07-mailer-password-reset.md)

**Status:** done

- [x] An Owner can invite by email with a role, and a copyable invite link is always available
- [x] Invite tokens are single-use, hashed and expiring, and Owners can revoke pending invites
- [x] Accepting as a new person creates an account and membership; accepting as an existing Member adds the membership
- [x] Pending invites are listed on the Members page
- [x] Invite, accept and revoke are recorded as Audit Events
- [x] End-to-end: Owner invites → email opened in Mailpit → accepted as a new account
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
