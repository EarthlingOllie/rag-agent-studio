# 04: Price table and overrides

**Ticket:** `02-04` · **Spec:** [Provider Credentials and Theme](../../specs/02-provider-credentials-theme-spec.md)

**What to build:** Owners see what each model costs according to the platform price table, and can override prices per credential for negotiated rates. A pure cost function makes these prices available to cost reporting.

**Blocked by:**
- [02-03: Model gateway and Default Model](03-model-gateway-default-model.md)

**Status:** ready-for-agent

- [ ] The price table lives in the repo as data with effective-from dates and is loaded on migrate
- [ ] Owners can override input, output and cached-token prices per credential
- [ ] The pure cost function prefers overrides and uses the price in effect at a given time
- [ ] The Studio shows prices with overrides
- [ ] Overrides are recorded as Audit Events
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
