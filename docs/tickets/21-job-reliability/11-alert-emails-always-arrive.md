# 11: Alert emails always arrive

**Ticket:** `21-11` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** The Token Budget exhausted, Evaluation budget spent, Block rate alert and Live score drop alert emails reach every Owner even if the process died between raising the alert and sending it.

**Blocked by:**
- `21-03`

**Status:** ready-for-agent

- [ ] Each of the four alerts records when it was raised and, separately, when it was sent to each Owner
- [ ] The sweeper sends any alert that is raised and not yet sent, to the Owners it has not reached
- [ ] A kill between raising and sending results in the email being sent by the next sweep
- [ ] A send that reached some Owners before failing is completed for the rest
- [ ] An alert is raised once per period as today; a second email to one Owner is possible only if the process died after sending and before recording it
- [ ] The Token Budget exhausted email, sent today from the API process, follows the same path
- [ ] Password reset and invite emails are unchanged
- [ ] Tests use the in-memory outbox and place the kill between raising and sending
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
