# 07: WCAG 2.2 AA widget

**Ticket:** `06-07` · **Spec:** [Embed, widget and Operational Settings](../../specs/06-embed-widget-operational-settings-spec.md)

**What to build:** Visitors using a keyboard or screen reader can use the widget fully, and automated checks prove AA compliance.

**Blocked by:**
- [06-03: Branded widget](03-branded-widget.md)

**Status:** ready-for-agent

- [ ] Keyboard users can open and close the widget, focus is trapped while it's open, and focus returns to the launcher afterwards
- [ ] A live region announces completed replies
- [ ] Controls are labelled, reduced-motion preferences are respected, and contrast meets AA
- [ ] axe in end-to-end tests reports zero AA violations in light and dark mode
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
