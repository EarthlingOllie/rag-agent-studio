# 01: Remove the VPC interface endpoints

**Ticket:** `22-01` · **Spec:** [Lean, scalable infrastructure](../../specs/22-lean-scalable-infrastructure-spec.md)

**What to build:** The demo stops paying for four interface endpoints. Tasks stay in private subnets and reach ECR, CloudWatch Logs and Secrets Manager through the NAT; image layers still come through the S3 gateway endpoint.

**Blocked by:**
- None

**Status:** done

- [x] The network module no longer creates the ECR API, ECR Docker, Logs and Secrets Manager interface endpoints or their security group
- [x] The S3 gateway endpoint, both subnet tiers, the `fck-nat` default and the managed-NAT toggle are unchanged
- [x] `terraform test` asserts there are no interface endpoints, the gateway endpoint is present and private subnets have no public IPs
- [x] The module's outputs and the demo environment still plan cleanly; nothing else referenced the endpoints
- [x] `make infra-check` passes, with any Checkov finding fixed or skipped with an inline reason
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## Evidence

- **No interface endpoints or their security group.** `infra/modules/network/main.tf` no longer declares `aws_vpc_endpoint.interface`, `aws_security_group.endpoints` or `aws_vpc_security_group_ingress_rule.endpoints_https`. The `endpoint_security_group_id` output went with them. Tasks reach ECR, CloudWatch Logs and Secrets Manager through the NAT.
- **Everything else is unchanged.** `aws_vpc_endpoint.s3` (Gateway, on the private route table), the public and private subnets, the `fck-nat` default and the `managed_nat` toggle are untouched. Their existing runs in `infra/modules/network/tests/contract.tftest.hcl` still pass: `spans_two_azs_with_public_and_private_subnets`, `egresses_through_fck_nat_by_default` and `managed_nat_toggle_swaps_fck_nat_for_a_nat_gateway`.
- **`terraform test` asserts the new shape.** The module has a new output, `vpc_endpoints`, which maps the service name of every endpoint it creates to that endpoint's type. `s3_is_the_only_vpc_endpoint` asserts the gateway endpoint and its route table, and asserts that `vpc_endpoints == { "com.amazonaws.eu-west-2.s3" = "Gateway" }`, so there are no interface endpoints. `s3_is_the_only_vpc_endpoint_with_a_managed_nat` asserts the same with the managed NAT. The existing `private_subnets_have_no_public_ips` run covers public IPs. The test was written first and failed (red), then the endpoints were removed (green).
- **Nothing else referenced the endpoints.** A grep found no use of `endpoint_security_group_id` or `aws_vpc_endpoint.interface` outside the network module. Three comments in `infra/modules/ecs` that said traffic went "through the VPC endpoints" now say "through the NAT". `infra/envs/demo` passes `terraform validate` and `terraform test` with mocked providers.
- **`make infra-check`.** It passes offline, with these exceptions: Terraform 1.13.4 was installed with `scripts/ci/install-tools.sh` and the AWS provider 6.72.0 was installed from a local filesystem mirror. TFLint could not run in this sandbox, because its GitHub download is blocked by the network policy. Checkov raised no new finding, and no skip was added.
- **Coverage and glossary.** This is an infra-only change at the module seam (`terraform test`), so no application code changed and no coverage changed. It adds no new domain term. ADR-0021 already records the decision.

## Gaps and best guesses

- **Deferred (needs a live deploy):** "the demo environment still plans cleanly" was checked only offline (`validate` plus mocked `terraform test`). The real `terraform plan` against state runs in the infra workflow's plan job or in 22-09. The plan should show the four interface endpoints, their security group and its ingress rule being destroyed, and nothing else.
- **TFLint was not run here** (blocked download). CI runs it.
- **Best guess:** `vpc_endpoints` is the module seam that proves there are no interface endpoints, because a test cannot refer to a resource that no longer exists.
- **Left for 22-08:** the deploy guide's cost table (`docs/deploy-demo.md`) still lists the interface endpoints. Ticket 22-08 recomputes that table for the new shape.
