# 01: Input Guardrail: local classifier, block mode

**Ticket:** `08-01` · **Spec:** [Guardrails and evaluation](../../specs/08-guardrails-evaluation-spec.md)

**What to build:** Every Visitor message is checked by a local prompt-injection classifier. In block mode, a detected attack never reaches the model: the Visitor gets the Agent's refusal text, and the Trace records why.

**Blocked by:**
- [04-06: Citations and Trace drawer](../04-agents-retrieval-playground/06-citations-trace.md)
- [06-01: Embed tracer](../06-embed-widget-operational-settings/01-embed-tracer.md)

**Status:** ready-for-agent

- [ ] A Guardrail pipeline wraps the runtime without changing its interface
- [ ] A local ONNX classifier adapter handles windowing, max score and a threshold; the model is baked into the image, with a live-suite test
- [ ] Block mode short-circuits with the refusal text and makes no model call
- [ ] Outcomes are saved on the Message and shown in the Trace
- [ ] The widget and Playground render refusals
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
