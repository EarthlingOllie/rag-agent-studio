# 05: Reranker

**Ticket:** `04-05` · **Spec:** [Agents, retrieval and Playground](../../specs/04-agents-retrieval-playground-spec.md)

**What to build:** An Editor can turn on a reranker, using a Voyage or Bedrock credential with rerank capability, so the best Chunks rise to the top.

**Blocked by:**
- [04-03: Hybrid retrieval and fallback](03-hybrid-retrieval-fallback.md)

**Status:** done

- [x] AgentConfig holds an optional reranker (a rerank-capable credential and model)
- [x] Candidates are reranked before the threshold and top-k are applied (tested with a fake reranker)
- [x] The reranker credential is registered as a reference
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
