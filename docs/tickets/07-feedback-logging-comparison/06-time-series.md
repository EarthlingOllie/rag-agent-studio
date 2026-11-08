# 06: Time series

**Ticket:** `07-06` · **Spec:** [Feedback, logging and comparison](../../specs/07-feedback-logging-comparison-spec.md)

**What to build:** Editors see key metrics over time, with markers where the Live Version changed, and a warning when Knowledge Base changes during the period may confound the comparison.

**Blocked by:**
- [07-04: Rollups and Version KPIs](04-rollups-version-kpis.md)

**Status:** done

- [x] A `time_series` query feeds a Recharts chart with Live History markers
- [x] Granularity and date range can be chosen
- [x] A confounder note appears when Documents changed during the period
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
