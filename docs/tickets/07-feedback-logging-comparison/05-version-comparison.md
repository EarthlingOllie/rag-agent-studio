# 05: Version comparison

**Ticket:** `07-05` · **Spec:** [Feedback, logging and comparison](../../specs/07-feedback-logging-comparison-spec.md)

**What to build:** Editors pick any two Versions of an Agent and compare their metrics side by side, with differences highlighted and the configuration diff alongside, and can export the comparison as CSV.

**Blocked by:**
- [07-04: Rollups and Version KPIs](04-rollups-version-kpis.md)
- [05-04: Diffs and Draft management](../05-versioning-project-instructions/04-diffs-draft-management.md)

**Status:** done

- [x] Any two Versions can be picked and shown side by side, with differences highlighted
- [x] The config diff is shown alongside the metrics
- [x] The comparison can be exported as CSV
- [x] A date range can be chosen
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

Evidence: [07-05-evidence/README.md](07-05-evidence/README.md).
