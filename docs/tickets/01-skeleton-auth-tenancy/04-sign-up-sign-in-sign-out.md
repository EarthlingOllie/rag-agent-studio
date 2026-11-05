# 04: Sign up, sign in, sign out

**Ticket:** `01-04` · **Spec:** [Skeleton, CI, auth and tenancy](../../specs/01-skeleton-auth-tenancy-spec.md)

**What to build:** A person signs up with their name, email, password and an Organisation name, and becomes the Owner of a new Organisation. They can sign in and out, and land in a clean Studio shell with navigation placeholders. All Organisation-scoped data access is tenant-scoped, and a shared cross-tenant isolation test harness exists for later tickets to extend.

**Blocked by:**
- [01-01: Walking skeleton](01-walking-skeleton.md)
- [01-02: Remaining CI gates and Playwright harness](02-ci-gates-playwright-harness.md)

**Status:** in-progress

- [ ] Sign-up creates the Organisation, the Member and an Owner membership in one transaction
- [ ] Passwords are hashed with argon2id; sessions are opaque, stored in Redis and held in an httpOnly, Secure, SameSite=Lax cookie that is rotated on sign-in
- [ ] Sign-out invalidates the session on the server
- [ ] Sign-in errors are identical whether or not the email is registered
- [ ] Data access below the platform level requires an Organisation in scope, and a parametrised isolation test asserts that other tenants' resources return 404
- [ ] Studio has sign-up and sign-in screens and a signed-in shell with Projects and Organisation settings placeholders
- [ ] End-to-end: sign up → see the signed-in shell → sign out
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
