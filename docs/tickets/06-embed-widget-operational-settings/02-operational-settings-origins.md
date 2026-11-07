# 02: Operational Settings and origin enforcement

**Ticket:** `06-02` · **Spec:** [Embed, widget and Operational Settings](../../specs/06-embed-widget-operational-settings-spec.md)

**What to build:** Editors manage an Agent's Allowed Origins (with validation, wildcards and localhost) and its unavailable text. Changes apply immediately without publishing and are audited. A page on a disallowed origin can't show the Agent.

**Blocked by:**
- [06-01: Embed tracer](01-embed-tracer.md)

**Status:** done

- [x] Operational Settings are separate from AgentConfig and apply on the next request
- [x] Allowed Origins are validated, including subdomain wildcards and localhost
- [x] The unavailable text can be set
- [x] Changes are recorded as Audit Events with before and after values
- [x] End-to-end: a page on a disallowed origin can't frame the widget
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
