# 01: Embed tracer

**Ticket:** `06-01` · **Spec:** [Embed, widget and Operational Settings](../../specs/06-embed-widget-operational-settings-spec.md)

**What to build:** An Editor copies an Agent's Embed Snippet into a web page, and a Visitor on that page chats with the Agent's Live Version, with streamed replies. The iframe is served with a `frame-ancestors` policy built from the Agent's Allowed Origins.

**Blocked by:**
- [05-02: Publish Agent to Live Version](../05-versioning-project-instructions/02-publish-agent-live-version.md)

**Status:** in-progress

- [ ] The Studio shows the Embed Snippet with a copy button, only once the Agent has a Live Version
- [ ] The loader script injects the iframe, and CI enforces a size budget for it
- [ ] The shell route sets `frame-ancestors` from Allowed Origins (a simple list) and issues a bootstrap token
- [ ] The bootstrap token is exchanged for a signed Conversation token, stored hashed
- [ ] Widget chat streams over SSE using the Live Version and its pinned Instructions; each Message is attributed to the Version that was Live when it was generated
- [ ] A demo host page is served on a separate origin in compose
- [ ] End-to-end: chat through the host page
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
