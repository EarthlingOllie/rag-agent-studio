# 01: API-key Provider Credentials

**Ticket:** `02-01` · **Spec:** [Provider Credentials and Theme](../../specs/02-provider-credentials-theme-spec.md)

**What to build:** Owners add Anthropic, OpenAI and Voyage Provider Credentials. Each is checked live when saved, encrypted, shown only as a masked suffix, and can be re-checked, rotated or deleted. Editors can see credentials but not manage them. A credential can't be deleted while something references it.

**Blocked by:**
- [01-09: Member management and role enforcement](../01-skeleton-auth-tenancy/09-member-management-roles.md)
- [01-11: TOTP MFA](../01-skeleton-auth-tenancy/11-totp-mfa.md)

**Status:** in-progress

- [ ] A KMS key-wrapper adapter sits alongside the local one, tested with a stubbed AWS client
- [ ] A credential records name, provider, auth kind, sealed secret, masked suffix, capabilities, check status and last-checked time
- [ ] A capability registry of providers, capabilities and models is exposed through the API
- [ ] A credential-verifier port with a fake adapter exists, and the Studio shows typed failure reasons
- [ ] Rotating keeps the credential's identity, and Owners can re-check on demand
- [ ] A reference registry lets consumers register references; deletion is blocked with the list of referencing items (tested with a test-registered reference)
- [ ] A response-schema test proves no endpoint ever returns secret material
- [ ] Mutations are Owner-only and Editors can read; everything is audited; tenant isolation tests are extended
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
