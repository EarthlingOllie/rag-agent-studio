# 05: Live score

**Ticket:** `15-05` · **Spec:** [Live evaluation](../../specs/15-live-evaluation-spec.md)

**What to build:** Each Version gets a Live score: a KPI card with its Wilson interval, a row in the Version comparison and CSV, and a Time series metric.

**Blocked by:**
- [15-01: Live Verdict tracer: sample a reply and judge it](01-live-verdict-tracer.md)

**Status:** ready-for-agent

- [ ] The Usage rollup gains Live Verdicts judged and passed per Agent Version and day, by the day of the reply; errors and skipped ones aren't counted
- [ ] A Live Verdict that arrives after its day's rollup is final doesn't move that day
- [ ] The Version KPIs gain the Live score with its Wilson interval and sample size, read from the rollups plus today's live partial day; only Visitor Conversations count
- [ ] The Live score card is marked Low sample under 30 judged Live Verdicts
- [ ] The Version comparison gains the Live score row (difference in percentage points, higher is the Better side, "(small sample)" marking) and its CSV column
- [ ] The Time series gains the Live score metric, with gaps where no reply was judged and the Live History markers
- [ ] The Live score reads the same before and after the Purge
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
