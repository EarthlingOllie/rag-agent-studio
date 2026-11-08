# 06: Token Budget

**Ticket:** `06-06` · **Spec:** [Embed, widget and Operational Settings](../../specs/06-embed-widget-operational-settings-spec.md)

**What to build:** Each Agent has a daily Token Budget. Once it's spent, Visitors see the unavailable message, the Agent shows an alert in the Studio, Owners get one email, and everything resets at midnight UTC.

**Blocked by:**
- [06-05: Rate limits](05-rate-limits.md)

**Status:** in-progress

- [ ] A daily counter per Agent per UTC date is incremented with actual usage
- [ ] An exhausted budget makes the Agent unavailable, shows an alert badge and sends one deduplicated email to Owners
- [ ] A Beat task clears alert flags at midnight UTC
- [ ] The Studio shows a budget meter, and the Playground is exempt
- [ ] End-to-end: exhausting a tiny budget shows the unavailable message
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
