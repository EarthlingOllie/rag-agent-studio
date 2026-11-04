# 05: CDN module

**Ticket:** `09-05` · **Spec:** [Terraform and deploy](../../specs/09-terraform-deploy-spec.md)

**What to build:** One CloudFront distribution serves the Studio, widget and API over TLS on its default domain, with SSE-safe settings for dynamic paths and an optional custom domain.

**Blocked by:**
- [09-04: Compute module](04-compute-module.md)

**Status:** ready-for-agent

- [ ] Each path has its own behaviour, and only static paths are cached
- [ ] Dynamic paths forward headers, cookies and query strings, and have a long read timeout
- [ ] A function provides SPA fallback routing
- [ ] An optional `domain_name` adds ACM and Route 53
- [ ] `terraform test` asserts the routing and the domain toggle
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
