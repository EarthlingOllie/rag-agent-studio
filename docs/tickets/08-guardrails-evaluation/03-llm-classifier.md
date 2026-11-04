# 03: LLM classifier

**Ticket:** `08-03` · **Spec:** [Guardrails and evaluation](../../specs/08-guardrails-evaluation-spec.md)

**What to build:** High-risk Agents can add an LLM classifier that uses the Agent's own Provider Credential, and Editors decide whether it fails open or closed when the provider errors.

**Blocked by:**
- [08-01: Input Guardrail: local classifier, block mode](01-input-guardrail-block.md)

**Status:** ready-for-agent

- [ ] A structured-output classifier runs through the model gateway
- [ ] Fail-open or fail-closed behaviour is configurable
- [ ] The classifier credential is registered as a reference
- [ ] Provider error paths are tested
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
