# 01: Prefactor: Chunk labels assigned per reply

**Ticket:** `13-01` · **Spec:** [Agentic retrieval](../../specs/13-agentic-retrieval-spec.md)

**What to build:** Nothing changes for Members or Visitors. The runtime keeps one per-reply record of the Chunks given to the model, which assigns their Chunk labels and resolves Citations, instead of deriving labels from each Chunk's rank. This makes adding several Searches per reply an easy change.

**Blocked by:**
- None

**Status:** done

- [x] The runtime assigns Chunk labels from a per-reply record of Chunks given to the model, in the order they were first given
- [x] Citations (structured output and label parsing) resolve through the same record
- [x] Automatic mode behaves exactly as before: the existing Playground, prompt-assembly, citation and canary tests pass unchanged
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
