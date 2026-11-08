# 06: Token Budget

**Ticket:** `06-06` · **Spec:** [Embed, widget and Operational Settings](../../specs/06-embed-widget-operational-settings-spec.md)

**What to build:** Each Agent has a daily Token Budget. Once it's spent, Visitors see the unavailable message, the Agent shows an alert in the Studio, Owners get one email, and everything resets at midnight UTC.

**Blocked by:**
- [06-05: Rate limits](05-rate-limits.md)

**Status:** done

- [x] A daily counter per Agent per UTC date is incremented with actual usage
- [x] An exhausted budget makes the Agent unavailable, shows an alert badge and sends one deduplicated email to Owners
- [x] A Beat task clears alert flags at midnight UTC
- [x] The Studio shows a budget meter, and the Playground is exempt
- [x] End-to-end: exhausting a tiny budget shows the unavailable message
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
