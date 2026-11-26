# 07: Lost Live Verdicts

**Ticket:** `21-07` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** A sampled reply whose judging job was lost or whose worker died is judged within minutes, tried once more at most, and then set to Error, so no Live Verdict stays Pending.

**Blocked by:**
- `21-02`
- `21-03`

**Status:** ready-for-agent

- [ ] A Live Verdict Pending for longer than its threshold is re-sent by the sweeper once
- [ ] A Live Verdict still Pending after its one re-send becomes an Error, which the Live score leaves out
- [ ] A re-sent verdict whose first job is somehow still running is judged once and its spend recorded once
- [ ] A verdict whose reply was Purged before the re-send is skipped, as today
- [ ] Live Verdicts already stuck on Pending when this ships are handled by the first sweep
- [ ] The threshold and the number of re-sends are settings
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
