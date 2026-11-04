# 03: Demo host pages

**Ticket:** `10-03` · **Spec:** [Seed data and showcase](../../specs/10-seed-showcase-spec.md)

**What to build:** An interviewer visits a fictional shop page with the Agent embedded as a bubble, an inline-layout page, and a disallowed-origin page that visibly fails. A low-budget Agent can be exhausted with one click.

**Blocked by:**
- [10-01: Seed foundation](01-seed-foundation.md)
- [06-06: Token Budget](../06-embed-widget-operational-settings/06-token-budget.md)

**Status:** ready-for-agent

- [ ] The shop pages (bubble and inline) are on an allowed origin
- [ ] A page on a disallowed origin is blocked
- [ ] A low-budget Agent has a button to exhaust its budget
- [ ] In AWS, the pages are served under the demo path
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
