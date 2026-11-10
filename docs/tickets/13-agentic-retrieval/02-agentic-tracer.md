# 02: Agentic tracer: one Knowledge Search, end to end

**Ticket:** `13-02` · **Spec:** [Agentic retrieval](../../specs/13-agentic-retrieval-spec.md)

**What to build:** An Editor can set an Agent's Retrieval Mode to Agentic through the Draft API. In the Playground, the model then makes a Knowledge Search, the Search appears as it happens, the answer cites what it found, and the Trace lists the Search with its Chunks.

**Blocked by:**
- [13-01: Prefactor: Chunk labels assigned per reply](01-per-reply-chunk-labels.md)

**Status:** in-progress

- [ ] AgentConfig Retrieval gains `mode` (`automatic` | `agentic`) and `search_limit` (1–5, default 3); `mode` defaults to **Automatic** until 13-09. The JSON Schema and generated client are updated and the client drift check passes
- [ ] In Agentic mode the runtime registers exactly one tool, Knowledge Search (argument: `query`), which calls the unchanged `retrieve` with the Agent's Retrieval settings and returns spotlighted, labelled data blocks; there is no upfront search
- [ ] The Agentic preamble rules are added and covered by the prompt-assembly contract test
- [ ] A `SearchEvent` is streamed as each Search starts and sent to the Playground as an SSE `search` event with its query
- [ ] A Search record (Message, order, query, latency, limit-refused) is persisted; Message retrievals reference their Search; Messages store `search_count`
- [ ] Token use is summed over every model call in the reply, and Cost is computed from the sums
- [ ] The Trace endpoint returns Searches in order with nested Message retrievals; the Playground shows a "Searching: …" line per Search, and the Trace drawer lists Searches with their Chunks
- [ ] Tag scoping and Project isolation hold for model-written queries (API seam, scripted `FunctionModel`)
- [ ] The default fake chat model searches once with the Visitor's question in Agentic mode; an end-to-end test sets an Agent to Agentic and sees a Search line, a cited answer and a Search in the Trace
- [ ] Automatic mode is unchanged
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
