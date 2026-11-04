# 03: Data modules

**Ticket:** `09-03` · **Spec:** [Terraform and deploy](../../specs/09-terraform-deploy-spec.md)

**What to build:** The database, cache, storage and KMS modules give the platform encrypted, private data stores ready for the application.

**Blocked by:**
- [09-02: Network module](02-network-module.md)

**Status:** ready-for-agent

- [ ] RDS runs Postgres 16, encrypted, private, with backups
- [ ] ElastiCache has encryption in transit and at rest, and auth enabled
- [ ] Buckets are private and encrypted; the Documents bucket's CORS rule allows only the CloudFront origin; static assets use origin access control
- [ ] The KMS key has rotation enabled
- [ ] `terraform test` asserts each of these
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
