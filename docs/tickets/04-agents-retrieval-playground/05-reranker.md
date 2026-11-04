# 05: Reranker

**Ticket:** `04-05` · **Spec:** [Agents, retrieval and Playground](../../specs/04-agents-retrieval-playground-spec.md)

**What to build:** An Editor can turn on a reranker, using a Voyage or Bedrock credential with rerank capability, so the best Chunks rise to the top.

**Blocked by:**
- [04-03: Hybrid retrieval and fallback](03-hybrid-retrieval-fallback.md)

**Status:** ready-for-agent

- [ ] AgentConfig holds an optional reranker (a rerank-capable credential and model)
- [ ] Candidates are reranked before the threshold and top-k are applied (tested with a fake reranker)
- [ ] The reranker credential is registered as a reference
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
