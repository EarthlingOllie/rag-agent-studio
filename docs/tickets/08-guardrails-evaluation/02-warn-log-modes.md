# 02: Warn and log modes

**Ticket:** `08-02` · **Spec:** [Guardrails and evaluation](../../specs/08-guardrails-evaluation-spec.md)

**What to build:** Editors choose warn (let the message through with an extra caution, and flag it) or log (record only) instead of block, to balance safety against false positives.

**Blocked by:**
- [08-01: Input Guardrail: local classifier, block mode](01-input-guardrail-block.md)

**Status:** done

- [x] Warn adds a caution block to the prompt and flags the Message
- [x] Log only records the verdict
- [x] The mode is part of the versioned AgentConfig, and tests cover each mode
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
