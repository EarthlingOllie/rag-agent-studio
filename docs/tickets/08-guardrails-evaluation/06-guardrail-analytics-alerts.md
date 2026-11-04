# 06: Guardrail analytics and alerts

**Ticket:** `08-06` · **Spec:** [Guardrails and evaluation](../../specs/08-guardrails-evaluation-spec.md)

**What to build:** Editors see each Version's Guardrail block rate, filter Conversations by Guardrail outcome, and get an alert badge when an Agent's block rate spikes.

**Blocked by:**
- [08-01: Input Guardrail: local classifier, block mode](01-input-guardrail-block.md)
- [07-04: Rollups and Version KPIs](../07-feedback-logging-comparison/04-rollups-version-kpis.md)
- [06-06: Token Budget](../06-embed-widget-operational-settings/06-token-budget.md)

**Status:** ready-for-agent

- [ ] The block rate is included in rollups and KPI cards
- [ ] Conversations can be filtered by Guardrail outcome
- [ ] A spike sets an alert flag and shows the badge
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
