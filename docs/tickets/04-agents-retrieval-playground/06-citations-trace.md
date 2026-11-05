# 06: Citations and Trace drawer

**Ticket:** `04-06` · **Spec:** [Agents, retrieval and Playground](../../specs/04-agents-retrieval-playground-spec.md)

**What to build:** Playground answers cite their sources, with chips that open the Document viewer. Every reply has a Trace showing model, tokens, cost, latency, and the retrieved Chunks with scores, which were cited, and which were excluded and why.

**Blocked by:**
- [04-03: Hybrid retrieval and fallback](03-hybrid-retrieval-fallback.md)
- [02-04: Price table and overrides](../02-provider-credentials-theme/04-price-table-overrides.md)

**Status:** in-progress

- [ ] Citations come from structured output where supported, falling back to label parsing, and resolve to Chunks
- [ ] Citation events are streamed, and Playground chips link to the Document viewer
- [ ] Each Chunk's retrieval is saved with score, rank, cited flag and any excluded reason
- [ ] Cost is computed with the cost function and stored on the Message
- [ ] A Trace endpoint and a Trace drawer show all of the above
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
