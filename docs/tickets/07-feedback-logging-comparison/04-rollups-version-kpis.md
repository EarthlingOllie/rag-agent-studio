# 04: Rollups and Version KPIs

**Ticket:** `07-04` · **Spec:** [Feedback, logging and comparison](../../specs/07-feedback-logging-comparison-spec.md)

**What to build:** Editors see each Agent Version's key numbers (volume, tokens, cost, thumbs-up rate with a 95% interval and sample size, mean rating, fallback rate and latency), with small samples visibly marked as low confidence.

**Blocked by:**
- [07-03: Conversation Rating](03-conversation-rating.md)

**Status:** done

- [x] `usage_daily` rollups run hourly for the current day and are finalised daily, idempotently, with histograms
- [x] The `version_metrics` query includes the live partial day and excludes the Playground
- [x] KPI cards show volume, mean and p95 tokens, cost per Conversation, thumbs-up rate with Wilson 95% interval and n, mean rating with n, fallback rate and p95 latency
- [x] Small samples get a low-confidence visual treatment
- [x] Wilson intervals and percentiles are tested against reference values
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

**Evidence:** [07-04-evidence/README.md](07-04-evidence/README.md)
