# 02: Remaining CI gates and Playwright harness

**Ticket:** `01-02` · **Spec:** [Skeleton, CI, auth and tenancy](../../specs/01-skeleton-auth-tenancy-spec.md)

**What to build:** Every CI workflow named in the plan exists and is green: security scanning, infrastructure checks on stub Terraform modules, image builds, a placeholder Guardrail evaluation job, and an end-to-end job that starts the compose stack and runs a Playwright smoke test against the Studio.

**Blocked by:**
- [01-01: Walking skeleton](01-walking-skeleton.md)

**Status:** ready-for-agent

- [ ] Security workflow runs gitleaks, pip-audit, pnpm audit and Trivy against the built images
- [ ] Infra workflow runs fmt, validate, tflint, checkov and `terraform test`, all passing on stub modules
- [ ] Deploy workflow builds images; push and apply steps are skipped cleanly when AWS secrets are absent
- [ ] Guardrail evaluation workflow exists as a passing placeholder
- [ ] End-to-end workflow starts compose, waits for health checks, and runs a Playwright smoke test with axe available
- [ ] Shared Playwright fixtures (stack readiness, signed-in page helpers) are ready for later tickets
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
