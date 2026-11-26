# 07: Scaling demonstration script

**Ticket:** `22-07` · **Spec:** [Lean, scalable infrastructure](../../specs/22-lean-scalable-infrastructure-spec.md)

**What to build:** One script puts real work on a deployed, seeded demo and prints a timeline of each service scaling out and back in, so the scaling can be shown and repeated.

**Blocked by:**
- `22-05`

**Status:** ready-for-agent

- [ ] The script takes the Studio URL and Owner credentials and needs a seeded demo
- [ ] It creates a throwaway Project, uploads the seed Documents several times under different names, starts Evaluation Runs on seeded Agents and sends API requests for a few minutes
- [ ] It polls ECS and CloudWatch and prints a timeline of queue depth and running tasks per service until every service is back at its minimum
- [ ] It deletes its Project when it finishes or is interrupted, so it can be run again
- [ ] It exits non-zero, saying which service, if a pool or the API never scaled out
- [ ] The load sizes and durations are arguments with defaults that finish in about fifteen minutes
- [ ] The deploy scripts' tests, with a stubbed `aws` and a stubbed API, cover the timeline and the clean-up
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
