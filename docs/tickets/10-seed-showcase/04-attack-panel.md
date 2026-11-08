# 04: Attack panel

**Ticket:** `10-04` · **Spec:** [Seed data and showcase](../../specs/10-seed-showcase-spec.md)

**What to build:** An interviewer clicks through one-click attacks against a demo Agent and sees each response and which Guardrail layer acted.

**Blocked by:**
- [10-02: Seeded history](02-seeded-history.md)
- [08-01: Input Guardrail: local classifier, block mode](../08-guardrails-evaluation/01-input-guardrail-block.md)
- [08-04: Canary token](../08-guardrails-evaluation/04-canary-token.md)

**Status:** done

- [x] The debug endpoint is enabled only in demo mode
- [x] There are buttons per attack category, plus a benign control
- [x] Each attack shows the stream and the per-layer Guardrail outcome
- [x] End-to-end tests assert each expected outcome
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
