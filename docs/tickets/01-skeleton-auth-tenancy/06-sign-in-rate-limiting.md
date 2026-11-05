# 06: Sign-in rate limiting and lockout

**Ticket:** `01-06` · **Spec:** [Skeleton, CI, auth and tenancy](../../specs/01-skeleton-auth-tenancy-spec.md)

**What to build:** Repeated failed sign-ins are slowed down and then temporarily locked out, per account and per IP, without revealing whether an account exists.

**Blocked by:**
- [01-04: Sign up, sign in, sign out](04-sign-up-sign-in-sign-out.md)

**Status:** in-progress

- [ ] Redis counters per account and per IP apply a progressive delay, then a temporary lockout
- [ ] The lockout expires as configured (tested with the controllable clock)
- [ ] Responses for an unknown email and a wrong password are indistinguishable
- [ ] The Studio shows a clear lockout message
- [ ] Lockouts are recorded as Audit Events
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
