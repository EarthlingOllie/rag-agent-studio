# 11: TOTP MFA

**Ticket:** `01-11` · **Spec:** [Skeleton, CI, auth and tenancy](../../specs/01-skeleton-auth-tenancy-spec.md)

**What to build:** Members can protect their account with an authenticator app. This ticket builds the envelope-encryption module (with the local key wrapper) that stores TOTP secrets and that Provider Credentials will reuse.

**Blocked by:**
- [01-04: Sign up, sign in, sign out](04-sign-up-sign-in-sign-out.md)

**Status:** in-progress

- [ ] The envelope-encryption module provides seal and open with AES-256-GCM, a fresh data key per record, a versioned format and a local key wrapper; tamper detection is tested
- [ ] Enrolment shows a QR code and requires a confirming code; ten single-use recovery codes are shown once and stored hashed
- [ ] Sign-in for an MFA-enabled Member returns an MFA-pending state, and a full session follows a valid code (±1 step) or a recovery code
- [ ] Disabling MFA requires the password and a code
- [ ] Enrolment, disabling and recovery-code use are recorded as Audit Events
- [ ] The Studio has screens for enrolment, the challenge and recovery codes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
