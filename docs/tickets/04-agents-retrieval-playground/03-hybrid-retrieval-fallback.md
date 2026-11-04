# 03: Hybrid retrieval and fallback

**Ticket:** `04-03` · **Spec:** [Agents, retrieval and Playground](../../specs/04-agents-retrieval-playground-spec.md)

**What to build:** Retrieval combines semantic and keyword search so exact terms are found. A minimum relevance threshold makes the Agent reply with its fallback text instead of guessing when nothing relevant is found.

**Blocked by:**
- [04-01: Agent and Playground tracer](01-agent-playground-tracer.md)

**Status:** ready-for-agent

- [ ] Full-text and vector results are fused with weighted RRF using the hybrid-weight setting
- [ ] When no Chunk passes the minimum score, the Agent replies with its fallback text
- [ ] Excluded candidates are returned with their reasons
- [ ] A fixture Knowledge Base covers hits only keyword search finds, the effect of weighting, the threshold, and isolation
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
