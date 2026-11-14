# 01: Prefactor: one public way to resolve an AgentConfig's models

**Ticket:** `14-01` · **Spec:** [Evaluation loop](../../specs/14-evaluation-loop-spec.md)

**What to build:** The Playground and widget serving resolve an AgentConfig's chat model, Reranker and LLM classifier through one public function, with no change in behaviour, so evaluation can resolve a Draft's or a Version's models without copying private helpers.

**Blocked by:**
- None

**Status:** ready-for-agent

- [ ] The chat model (Model override, else the Default Model), the Reranker and the LLM classifier are resolved from an AgentConfig by one public function in one module, returning typed choices or a typed error (no Default Model, Provider Credential gone)
- [ ] The Playground and widget serving both use it; the private helpers it replaces are removed
- [ ] Automatic fallback for a model without Tool support still happens where it did
- [ ] Every existing Playground, serving and Guardrail test passes unchanged; the function's refusals are covered at the API seam through the existing Playground and widget routes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
