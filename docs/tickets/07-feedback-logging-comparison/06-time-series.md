# 06: Time series

**Ticket:** `07-06` · **Spec:** [Feedback, logging and comparison](../../specs/07-feedback-logging-comparison-spec.md)

**What to build:** Editors see key metrics over time, with markers where the Live Version changed, and a warning when Knowledge Base changes during the period may confound the comparison.

**Blocked by:**
- [07-04: Rollups and Version KPIs](04-rollups-version-kpis.md)

**Status:** in-progress

- [ ] A `time_series` query feeds a Recharts chart with Live History markers
- [ ] Granularity and date range can be chosen
- [ ] A confounder note appears when Documents changed during the period
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
