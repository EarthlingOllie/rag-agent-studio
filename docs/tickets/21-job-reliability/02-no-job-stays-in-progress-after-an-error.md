# 02: No job stays in progress after an error

**Ticket:** `21-02` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** A sampled reply is judged and charged once however often its job runs, and an Evaluation Run, Suggestion run or Live Verdict that hits an unexpected error ends in a state a person can see instead of staying in progress.

**Blocked by:**
- None

**Status:** ready-for-agent

- [ ] The Live Verdict job does nothing unless the verdict is Pending; a second run after the first finished makes no judge call and records no spend
- [ ] Spend for a Live Verdict is recorded in the same conditional update that stores the verdict, so two copies racing record it once; no row lock is held across the judge call
- [ ] An Evaluation Run whose job raises an unexpected error ends as Failed with a readable reason and frees the Agent for another Run
- [ ] A Suggestion run whose job raises an unexpected error ends as Failed, and its check Run, if one was started, is ended too
- [ ] A Live Verdict whose job raises an unexpected error becomes an Error, which the Live score leaves out
- [ ] A Suggestion run that finds its check Run already in progress no longer crashes: it settles by the same rule
- [ ] Tests count judge calls on the fake chat model and read spend back through the API
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
