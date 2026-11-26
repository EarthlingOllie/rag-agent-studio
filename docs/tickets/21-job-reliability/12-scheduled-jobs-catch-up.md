# 12: Scheduled jobs catch up

**Ticket:** `21-12` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** The Purge, the Block rate alert check and the daily reset of Token Budget alerts all make up for a run that was missed while Beat was down, so a deploy never skips them.

**Blocked by:**
- None

**Status:** ready-for-agent

- [ ] The Purge runs hourly; a missed run leaves Message text at most an hour past its Retention Window
- [ ] The Block rate alert check records the last hour it covered and checks every hour since, so a spike during an outage is still alerted on
- [ ] The Token Budget alert reset keys on the UTC date: a run after a missed midnight resets the day that ended
- [ ] Usage rollups stay correct when their job runs twice or late (already true; a test pins it)
- [ ] The test that asserts the Beat schedule reflects the hourly Purge
- [ ] Tests use the controllable clock to skip a midnight, a Purge and several block-rate hours
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
