# 01: Embed tracer

**Ticket:** `06-01` · **Spec:** [Embed, widget and Operational Settings](../../specs/06-embed-widget-operational-settings-spec.md)

**What to build:** An Editor copies an Agent's Embed Snippet into a web page, and a Visitor on that page chats with the Agent's Live Version, with streamed replies. The iframe is served with a `frame-ancestors` policy built from the Agent's Allowed Origins.

**Blocked by:**
- [05-02: Publish Agent to Live Version](../05-versioning-project-instructions/02-publish-agent-live-version.md)

**Status:** done

- [x] The Studio shows the Embed Snippet with a copy button, only once the Agent has a Live Version
- [x] The loader script injects the iframe, and CI enforces a size budget for it
- [x] The shell route sets `frame-ancestors` from Allowed Origins (a simple list) and issues a bootstrap token
- [x] The bootstrap token is exchanged for a signed Conversation token, stored hashed
- [x] Widget chat streams over SSE using the Live Version and its pinned Instructions; each Message is attributed to the Version that was Live when it was generated
- [x] A demo host page is served on a separate origin in compose
- [x] End-to-end: chat through the host page
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
