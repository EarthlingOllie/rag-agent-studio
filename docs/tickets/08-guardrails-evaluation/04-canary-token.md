# 04: Canary token

**Ticket:** `08-04` · **Spec:** [Guardrails and evaluation](../../specs/08-guardrails-evaluation-spec.md)

**What to build:** Every prompt carries a secret canary token. If a reply starts to leak it, even split across stream chunks, the stream is cut and replaced with the fallback text before any fragment reaches the Visitor.

**Blocked by:**
- [04-06: Citations and Trace drawer](../04-agents-retrieval-playground/06-citations-trace.md)

**Status:** done

- [x] A per-request canary is placed in the platform preamble
- [x] A streaming filter holds back a buffer as long as the canary, then cuts the stream and emits a replace event
- [x] Table-driven tests cover every split position and near misses
- [x] A post-completion check of the normalised text logs and flags encoded leaks, and the limitation is documented
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
