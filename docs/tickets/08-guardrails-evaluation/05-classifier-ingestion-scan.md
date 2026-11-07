# 05: Classifier-based ingestion scan

**Ticket:** `08-05` · **Spec:** [Guardrails and evaluation](../../specs/08-guardrails-evaluation-spec.md)

**What to build:** The ingestion scan uses the local classifier. Each Project chooses whether flagged Chunks are only marked or excluded from retrieval. Editors can clear false positives.

**Blocked by:**
- [08-01: Input Guardrail: local classifier, block mode](01-input-guardrail-block.md)
- [03-07: Heuristic ingestion scan](../03-projects-knowledge-base/07-heuristic-ingestion-scan.md)
- [04-03: Hybrid retrieval and fallback](../04-agents-retrieval-playground/03-hybrid-retrieval-fallback.md)

**Status:** in-progress

- [ ] Ingestion uses the local classifier adapter
- [ ] A per-Project mark or exclude setting exists, and retrieval honours exclude
- [ ] Clearing a flag is an Editor action and is audited
- [ ] Excluded flagged Chunks appear in the Trace's excluded reasons
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
