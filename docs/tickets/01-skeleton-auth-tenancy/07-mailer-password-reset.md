# 07: Mailer, password reset and change password

**Ticket:** `01-07` · **Spec:** [Skeleton, CI, auth and tenancy](../../specs/01-skeleton-auth-tenancy-spec.md)

**What to build:** Members can reset a forgotten password through an emailed link, and change their password and name from their Profile. Both password flows end the Member's other sessions. Email goes through a pluggable mailer.

**Blocked by:**
- [01-04: Sign up, sign in, sign out](04-sign-up-sign-in-sign-out.md)

**Status:** in-progress

- [ ] The mailer port has SES, SMTP (Mailpit) and in-memory outbox adapters, selected by settings
- [ ] Requesting a reset always returns the same response; reset links are single-use and expiring, and tokens are stored hashed
- [ ] Completing a reset or changing a password revokes the Member's other sessions
- [ ] The Profile page lets a Member edit their name and change their password (current password required)
- [ ] Resets and password changes are recorded as Audit Events
- [ ] End-to-end: request a reset → open the email in Mailpit → set a new password → sign in
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
