# 07: Attack evaluation suite

**Ticket:** `08-07` · **Spec:** [Guardrails and evaluation](../../specs/08-guardrails-evaluation-spec.md)

**What to build:** A versioned set of attack and benign prompts runs through the real Guardrail pipeline on every PR against a deliberately naive mocked model, and nightly against a real model, producing a pass-rate report.

**Blocked by:**
- [08-02: Warn and log modes](02-warn-log-modes.md)
- [08-04: Canary token](04-canary-token.md)
- [08-05: Classifier-based ingestion scan](05-classifier-ingestion-scan.md)

**Status:** ready-for-agent

- [ ] A case-file schema covers the attack categories and benign controls
- [ ] The runner drives the real pipeline with a naive `FunctionModel` that would comply with injected instructions
- [ ] Reports are produced as JSON and a markdown summary
- [ ] The Guardrail evaluation CI job fails on any unexpected outcome
- [ ] The nightly live job publishes its report and fails below the configured pass rate
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
