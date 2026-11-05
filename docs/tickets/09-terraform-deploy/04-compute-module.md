# 04: Compute module

**Ticket:** `09-04` · **Spec:** [Terraform and deploy](../../specs/09-terraform-deploy-spec.md)

**What to build:** The compute module runs the API, worker and Beat on Fargate behind an ALB that only CloudFront can reach, each with a least-privilege role, secrets injected from Secrets Manager, and images from ECR.

**Blocked by:**
- [09-03: Data modules](03-data-modules.md)

**Status:** in-progress

- [ ] An ECS cluster runs three ARM64 services, with task sizes set by variables
- [ ] Each service has a least-privilege role (policy documents asserted in tests), and the API's assume-role permission requires an external ID
- [ ] The ALB security group allows only the CloudFront prefix list, and a listener rule requires the secret header
- [ ] ECR scans images on push and has a lifecycle rule
- [ ] Secrets are injected from Secrets Manager, and log groups have retention set
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
