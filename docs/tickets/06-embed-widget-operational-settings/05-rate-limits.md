# 05: Rate limits

**Ticket:** `06-05` · **Spec:** [Embed, widget and Operational Settings](../../specs/06-embed-widget-operational-settings-spec.md)

**What to build:** Visitors who flood an Agent are slowed per Conversation and per IP, and see the Agent's unavailable text rather than an error.

**Blocked by:**
- [06-02: Operational Settings and origin enforcement](02-operational-settings-origins.md)

**Status:** done

- [x] Admission control applies per-token and per-IP sliding windows in Redis, using limits from Operational Settings
- [x] Client IP extraction trusts only the configured proxies (table-tested)
- [x] Refusals stream an unavailable event, and the widget shows the unavailable text
- [x] The Playground is exempt
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
