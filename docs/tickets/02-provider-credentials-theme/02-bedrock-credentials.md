# 02: Bedrock credentials

**Ticket:** `02-02` · **Spec:** [Provider Credentials and Theme](../../specs/02-provider-credentials-theme-spec.md)

**What to build:** Owners connect Bedrock either by letting the platform assume a role in their AWS account (preferred, since no secret is stored) or with access keys. The Studio shows exactly what to paste into AWS.

**Blocked by:**
- [02-01: API-key Provider Credentials](01-api-key-credentials.md)

**Status:** ready-for-agent

- [ ] Role-based credentials use a role ARN plus a platform-generated, per-Organisation external ID, and the Studio shows the trust policy to paste
- [ ] Access key, secret and region are accepted as a fallback
- [ ] The verifier checks role assumption, then model access; STS sessions are cached until shortly before they expire (controllable clock)
- [ ] Failures give clear reasons: role not assumable, no model access, wrong region
- [ ] The UI recommends the role option
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
