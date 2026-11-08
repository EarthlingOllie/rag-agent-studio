# 08: Organisation cost page

**Ticket:** `07-08` · **Spec:** [Feedback, logging and comparison](../../specs/07-feedback-logging-comparison-spec.md)

**What to build:** Owners see what the Organisation spent over a period, by Project and by Agent, with Playground usage shown separately.

**Blocked by:**
- [07-04: Rollups and Version KPIs](04-rollups-version-kpis.md)

**Status:** in-progress

- [ ] The `org_cost` query groups by Project or Agent for a period, with Playground usage in a separate column
- [ ] There's an Owner-only cost page
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
