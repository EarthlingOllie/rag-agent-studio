# 02: Search limit, Fallback Text and turn-wide Chunk labels

**Ticket:** `13-02` · **Spec:** [Agentic retrieval](../../specs/13-agentic-retrieval-spec.md)

**What to build:** Agentic replies are bounded by the Search limit, still give the Fallback Text when nothing relevant exists, and cite Chunks found by several Searches correctly.

**Blocked by:**
- [13-01: Agentic tracer](01-agentic-tracer.md)

**Status:** ready-for-agent

- [ ] A Knowledge Search call beyond the Search limit is refused with "search limit reached; answer from what you have"; the reply still answers and the Trace shows limit-hit
- [ ] If the model searched and no Search found a Chunk reaching the Minimum Score, the Fallback Text is sent instead of the model's answer, with no answer tokens streamed first, and `fallback` is true
- [ ] A reply that made no Search (a greeting) answers normally and is not a fallback
- [ ] Chunk labels continue across Searches; a Chunk found twice keeps its first label and isn't sent to the model again
- [ ] Citations resolve across every Chunk given to the model in the reply, through structured output and label parsing
- [ ] A provider error after a Search ends the reply with a typed error event
- [ ] When the effective model loses tool support (Default Model changed), the reply runs as Automatic and the Trace carries a warning, shown in the Trace drawer
- [ ] Remembered turns replay only Visitor and Agent text
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
