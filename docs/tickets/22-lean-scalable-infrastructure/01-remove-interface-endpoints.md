# 01: Remove the VPC interface endpoints

**Ticket:** `22-01` · **Spec:** [Lean, scalable infrastructure](../../specs/22-lean-scalable-infrastructure-spec.md)

**What to build:** The demo stops paying for four interface endpoints. Tasks stay in private subnets and reach ECR, CloudWatch Logs and Secrets Manager through the NAT; image layers still come through the S3 gateway endpoint.

**Blocked by:**
- None

**Status:** ready-for-agent

- [ ] The network module no longer creates the ECR API, ECR Docker, Logs and Secrets Manager interface endpoints or their security group
- [ ] The S3 gateway endpoint, both subnet tiers, the `fck-nat` default and the managed-NAT toggle are unchanged
- [ ] `terraform test` asserts there are no interface endpoints, the gateway endpoint is present and private subnets have no public IPs
- [ ] The module's outputs and the demo environment still plan cleanly; nothing else referenced the endpoints
- [ ] `make infra-check` passes, with any Checkov finding fixed or skipped with an inline reason
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
