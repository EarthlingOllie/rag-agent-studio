# 06: On-demand CI job and guide

**Ticket:** `23-06` · **Spec:** [Rehearsing the AWS deployment on Floci](../../specs/23-floci-rehearsal-spec.md)

**What to build:** The rehearsal can be run from GitHub Actions on a pull request that touches the infrastructure, and the guide says what it proves and what only AWS proves.

**Blocked by:**
- `23-04`

**Status: done.** Every criterion is met and evidenced below, except that the workflow has not yet run on GitHub (it can only run once pushed to the default branch or dispatched on this branch by the owner): see the gaps.

- [x] A workflow run by hand runs `make rehearse` and `make rehearse-down` and uploads the logs; it is not a required check. It logs in to Docker Hub or pulls the emulator's images from a mirror (23-01 hit Docker Hub's rate limit)
- [x] The `local` environment is part of `make infra-check` and the infra workflow
- [x] The deploy guide gains a rehearsal section: prerequisites, the commands, what the rehearsal proves, and what it does not (IAM, security groups, the CloudFront Function, Spot interruptions, Bedrock, ECS task protection through the agent, the pools' metric-math alarms)
- [x] The README's testing table lists `make rehearse`
- [x] `make link-check` passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## Evidence

**The on-demand workflow.** [`.github/workflows/rehearsal.yml`](../../../.github/workflows/rehearsal.yml) runs only on `workflow_dispatch` (Actions, rehearsal, Run workflow, on any branch), so it is never a required check. It installs the frontend's dependencies, logs in to Docker Hub when the `DOCKERHUB_USERNAME` variable and `DOCKERHUB_TOKEN` secret are set and otherwise sets `REHEARSAL_IMAGE_MIRROR=mirror.gcr.io` (ticket 23-01 hit the anonymous pull limit; `rehearse.sh` already pulls through a mirror and tags the names Floci asks for, `up_pulls_through_a_docker_hub_mirror_and_tags_the_names_floci_asks_for`), then runs `make rehearse`, `make rehearse-seed`, optionally `make rehearse-scale` (a boolean input), collects Floci's and every task container's log, always runs `make rehearse-down`, and uploads everything as the `rehearsal-logs` artifact (14 days). Nothing in it holds AWS credentials: terraform and the AWS CLI run on the rehearsal's internal tools network with dummy credentials.

**`local` in `make infra-check` and the infra workflow.** `TF_ROOTS` in the Makefile is every `infra/envs/*/main.tf`, so `infra/envs/local` gets `fmt`, `validate`, `terraform test` (11 runs), `tflint` and `checkov` like the demo, and `infra/tests/compose.test.sh` checks it composes the demo's modules; the infra workflow's `checks` job runs `make infra-check` on every push and pull request. The rehearsal's own tests run there too: `rehearse.test.sh`, `drive-scaling.test.sh`, `smoke.test.sh` and the front end's Node tests ([23-05's infra-check.log](23-05-evidence/infra-check.log), the same tree apart from this ticket's workflow and documents).

**The guide.** [docs/deploy-demo.md](../../deploy-demo.md#rehearse-it-on-floci-no-aws-account) gained "Rehearse it on Floci (no AWS account)": prerequisites (Docker socket, memory, port 4566, Docker Hub limit and mirror, architectures), the four commands and the workflow, what the rehearsal proves, and what only AWS proves: IAM and security groups, the CloudFront Function (the front end runs its file, CloudFront is not proven), Spot interruptions, Bedrock, ECS task protection through the agent, the pools' metric-math alarms (and ECS's CPU metric), sizes and cold starts, the seed log's first page, and database TLS and HTTPS at the edge. Deep links are listed under the CloudFront Function, and the seed log page under its own item, as 23-04 asked.

**README.** The testing table lists `make rehearse` (with the seed, scale and down targets) and links the guide.

**Links, tests, glossary.** `make link-check` passes ([link-check.log](23-06-evidence/link-check.log)). The workflow has no unit seam; its steps are the Make targets, each tested by `rehearse.test.sh`. No backend or frontend code changed. No new domain term; no ADR decision changed.

## Gaps and best guesses

- **The workflow has not run on GitHub.** `workflow_dispatch` workflows appear in the Actions tab once the file is on the default branch; it was written to match the commands run by hand in 23-03 to 23-05. Human-eyes: run it once (on this branch after merge), and set `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` if `mirror.gcr.io` is not wanted.
- **Runner memory.** GitHub's standard Linux runner has 16 GB for public repositories; a private repository's smaller standard runner may fail `rehearse.sh`'s 8 GB check with a clear message. A larger runner label is the fix there; left as `ubuntu-latest`.
- **Image builds use Docker Hub's base images** (`python:3.13-slim`, `node:22-slim`) even with the mirror, so heavy use without a login can still hit the limit during `make images`.
