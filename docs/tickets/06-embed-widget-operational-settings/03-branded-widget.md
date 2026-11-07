# 03: Branded widget

**Ticket:** `06-03` · **Spec:** [Embed, widget and Operational Settings](../../specs/06-embed-widget-operational-settings-spec.md)

**What to build:** Visitors see a widget that looks like the host site: the Organisation Theme with any per-Agent override, a bubble or inline launcher, the Agent's greeting, starter questions, custom UI text and citations, and a full-screen layout on phones.

**Blocked by:**
- [06-01: Embed tracer](01-embed-tracer.md)
- [02-05: Theme editor](../02-provider-credentials-theme/05-theme-editor.md)

**Status:** in-progress

- [ ] The shell inlines the resolved Theme plus the per-Agent override, which is Owner-only and not versioned
- [ ] Bubble and inline launchers are chosen by data attributes, with postMessage resizing that validates the message origin
- [ ] Greeting, starter questions, UI text and citations come from the Live Version
- [ ] Phones get a full-screen layout
- [ ] Light, dark and auto modes work
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
