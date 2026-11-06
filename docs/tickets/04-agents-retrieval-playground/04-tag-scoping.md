# 04: Tag scoping

**Ticket:** `04-04` · **Spec:** [Agents, retrieval and Playground](../../specs/04-agents-retrieval-playground-spec.md)

**What to build:** An Editor limits an Agent to Documents with certain Tags, so several Agents can share one Project but see different material.

**Blocked by:**
- [04-03: Hybrid retrieval and fallback](03-hybrid-retrieval-fallback.md)
- [03-06: Tags](../03-projects-knowledge-base/06-tags.md)

**Status:** done

- [x] AgentConfig holds Tag IDs, and retrieval filters by them
- [x] Unknown Tags, or Tags from another Project, are rejected
- [x] Deleting a Tag that Agents reference warns which Agents use it
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
