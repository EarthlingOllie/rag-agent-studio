# 01: State bootstrap and CI OIDC

**Ticket:** `09-01` · **Spec:** [Terraform and deploy](../../specs/09-terraform-deploy-spec.md)

**What to build:** A one-time bootstrap creates the Terraform state bucket and the GitHub OIDC deploy role. After that, PRs touching infrastructure get a `terraform plan`, and the plan job is skipped cleanly when AWS isn't configured.

**Blocked by:**
- [01-02: Remaining CI gates and Playwright harness](../01-skeleton-auth-tenancy/02-ci-gates-playwright-harness.md)

**Status:** ready-for-agent

- [ ] A bootstrap root module creates a versioned, encrypted state bucket
- [ ] The S3 backend uses native locking (`use_lockfile`)
- [ ] The `ci-oidc` module trusts only this repository
- [ ] The plan-on-PR job runs when the secret is present and is skipped otherwise
- [ ] Bootstrap steps are documented
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
