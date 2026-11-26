# 08: A Re-embed survives interruption

**Ticket:** `21-08` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** A Re-embed whose worker died, or whose job or retry was lost, carries on from the Chunks it had not yet done, and fails cleanly if it keeps being interrupted.

**Blocked by:**
- `21-03`

**Status:** ready-for-agent

- [ ] Re-embed jobs gain a heartbeat and claim through the job reliability module
- [ ] A Re-embed with no heartbeat for 5 minutes is re-sent and resumes from the Chunks still missing the pending model's vector
- [ ] A Re-embed whose first message or retry was lost starts within the queued-too-long time
- [ ] Two copies of one Re-embed never embed the same batch: the second fails to claim and exits. Tests count calls on the fake embedder
- [ ] A Re-embed interrupted three times with no new Chunks embedded in between fails through the existing failure path, leaving the active Embedding Model unchanged and saying why
- [ ] Choosing the pending model again after such a failure starts a fresh Re-embed
- [ ] Re-embeds already stuck when this ships are resumed by the first sweep
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
