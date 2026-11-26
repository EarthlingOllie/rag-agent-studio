# 04: Two worker pools

**Ticket:** `22-04` · **Spec:** [Lean, scalable infrastructure](../../specs/22-lean-scalable-infrastructure-spec.md)

**What to build:** On AWS the worker becomes a general pool on Fargate Spot and a runs pool on regular Fargate, each serving its own queue, so a long Evaluation Run no longer holds up ingestion and work that restarts for free runs on the cheapest capacity.

**Blocked by:**
- `22-03`

**Status:** ready-for-agent

- [ ] The compute module's services are `api`, `worker-general`, `worker-runs` and `beat`; both worker services run the backend image with their queue
- [ ] The cluster has the Fargate and Fargate Spot capacity providers; `worker-general` uses Spot unless `worker_spot` is false; `worker-runs` uses regular Fargate
- [ ] Sizes are variables: `worker-general` 2 vCPU / 8 GB, `worker-runs` 1 vCPU / 4 GB, confirmed or corrected by measuring a Run's memory with the local Embedding Model and the Guardrail classifier loaded
- [ ] Worker tasks have a two-minute stop timeout
- [ ] Each pool's task role may receive only from its own queue and send to both; each pool keeps only the storage and key permissions its jobs need
- [ ] The database and cache admit both pools; Beat is unchanged
- [ ] The deploy script rolls `api`, both pools and `beat` and reports each as stable; the seed task queues its ingestion and waits for the general pool as before
- [ ] `terraform test` asserts the four services and their commands, the Spot strategy and its off switch, the stop timeout and each role's policy document
- [ ] The deploy scripts' tests cover the services rolled
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
