# 06: Demo environment and deploy workflow

**Ticket:** `09-06` · **Spec:** [Terraform and deploy](../../specs/09-terraform-deploy-spec.md)

**What to build:** A developer brings the demo environment up at a chosen image tag with one workflow run, and tears it down with another. Migrations run before services roll, and a smoke check confirms the deploy works.

**Blocked by:**
- [09-01: State bootstrap and CI OIDC](01-state-bootstrap-oidc.md)
- [09-05: CDN module](05-cdn-module.md)
- [06-01: Embed tracer](../06-embed-widget-operational-settings/01-embed-tracer.md)

**Status:** ready-for-agent

- [ ] `envs/demo` composes all the modules
- [ ] The deploy workflow applies at a tag, runs the migration task, waits for services to stabilise, uploads static assets, invalidates the cache, and runs a smoke check (health, Studio, widget CSP)
- [ ] Destroy is a separate workflow with a typed confirmation
- [ ] Outputs include the CloudFront URL and the trust principal
- [ ] The expected cost is documented
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
