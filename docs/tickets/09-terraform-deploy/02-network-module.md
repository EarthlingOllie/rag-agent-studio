# 02: Network module

**Ticket:** `09-02` · **Spec:** [Terraform and deploy](../../specs/09-terraform-deploy-spec.md)

**What to build:** The network module provides a private, cheap VPC: public and private subnets across two AZs, `fck-nat` egress by default with a managed-NAT toggle, and VPC endpoints to cut NAT traffic.

**Blocked by:**
- [01-02: Remaining CI gates and Playwright harness](../01-skeleton-auth-tenancy/02-ci-gates-playwright-harness.md)

**Status:** ready-for-agent

- [ ] The VPC spans two AZs with public and private subnets
- [ ] `fck-nat` is the default, with a managed-NAT toggle
- [ ] VPC endpoints exist for S3, ECR, Logs and Secrets Manager
- [ ] `terraform test` asserts the toggle and that private subnets have no public IPs
- [ ] Every resource carries the standard tags
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
