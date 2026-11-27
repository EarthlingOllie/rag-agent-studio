# 06: On-demand CI job and guide

**Ticket:** `23-06` · **Spec:** [Rehearsing the AWS deployment on Floci](../../specs/23-floci-rehearsal-spec.md)

**What to build:** The rehearsal can be run from GitHub Actions on a pull request that touches the infrastructure, and the guide says what it proves and what only AWS proves.

**Blocked by:**
- `23-04`

**Status:** ready-for-agent

- [ ] A workflow run by hand runs `make rehearse` and `make rehearse-down` and uploads the logs; it is not a required check. It logs in to Docker Hub or pulls the emulator's images from a mirror (23-01 hit Docker Hub's rate limit)
- [ ] The `local` environment is part of `make infra-check` and the infra workflow
- [ ] The deploy guide gains a rehearsal section: prerequisites, the commands, what the rehearsal proves, and what it does not (IAM, security groups, the CloudFront Function, Spot interruptions, Bedrock, ECS task protection through the agent, the pools' metric-math alarms)
- [ ] The README's testing table lists `make rehearse`
- [ ] `make link-check` passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
