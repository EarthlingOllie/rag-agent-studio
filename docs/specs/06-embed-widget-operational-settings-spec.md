# Spec 06: Embed, widget and Operational Settings

## Problem Statement

An Agent only creates value once it's in front of real people on the Organisation's own website. Organisations want to drop it in with a snippet of code and have it look like their brand, and they need confidence that it can't be lifted onto someone else's site, run up their model bill, or break their page. Visitors want something fast, accessible and familiar that remembers their Conversation if they reload the page. When the Agent has to stop answering (a budget is spent or limits are hit), Visitors should see a polite message, not a stack trace, and the Organisation should be told.

## Solution

Every Agent with a Live Version gets an Embed Snippet: one `<script>` tag that injects an iframe served from the platform.
- **Allowed sites.** The iframe's HTML is served by the API with a `frame-ancestors` policy built from the Agent's Allowed Origins, so browsers refuse to show it on other sites.
- **Branding and accessibility.** The widget applies the Organisation's Theme plus any per-Agent colour and avatar override, offers a floating bubble or an inline container, and targets WCAG 2.2 AA.
- **Visitor flow.** Visitors chat anonymously with streamed replies and citations, and their Conversation resumes within 24 hours.
- **Protection.** Signed Conversation tokens, per-token and per-IP rate limits, and a daily Token Budget per Agent. When a limit is hit, Visitors see the Agent's "temporarily unavailable" text, the Agent shows an alert in the Studio, and Owners are emailed.
- **Operational Settings.** Allowed Origins, rate limits, Token Budget and the unavailable text are edited separately from Versions, take effect immediately and are audited.

## User Stories

1. As an Editor, I want to copy an Agent's Embed Snippet from the Studio, so that our web team can add it to our site.
2. As an Editor, I want the snippet to include optional attributes for launcher type and inline container, so that one snippet format covers both layouts.
3. As an Editor, I want the Embed Snippet unavailable until the Agent has a Live Version, so that a half-configured Agent can't be embedded.
4. As an Editor, I want to manage an Agent's Allowed Origins as a list of sites, so that only our own sites can show it.
5. As an Editor, I want Allowed Origins validated (scheme plus host, optional port, optional subdomain wildcard), so that I can't save a malformed rule.
6. As an Editor, I want localhost origins allowed explicitly for development, so that our developers can test the embed.
7. As an Editor, I want changes to Allowed Origins to take effect immediately without publishing, so that adding a new site is quick.
8. As an Editor, I want to set per-Conversation and per-IP rate limits, so that one person can't flood the Agent.
9. As an Editor, I want to set a daily Token Budget per Agent, so that spend is capped even under abuse.
10. As an Editor, I want to see today's token use against the budget, so that I know how close we are.
11. As an Editor, I want to set the "temporarily unavailable" text, so that Visitors get an on-brand message when limits are hit.
12. As an Owner, I want every Operational Settings change recorded as an Audit Event with before and after values, so that I can see who opened up an origin or raised a budget.
13. As an Owner, I want to override the Theme's colours and avatar for a specific Agent, so that sub-brands can share one Organisation.
14. As a Visitor, I want a launcher bubble in the corner of the page that opens the chat, so that it's available without getting in the way.
15. As a Visitor, I want the inline layout to fit naturally where the site placed it, so that it feels part of the page.
16. As a Visitor, I want the widget to look like the site I'm on, in the right colours, font, logo and light or dark mode, so that I trust it.
17. As a Visitor, I want to see the Agent's greeting and starter questions, so that I know what I can ask.
18. As a Visitor, I want replies to stream in as they're written, so that the Agent feels responsive.
19. As a Visitor, I want citations I can expand to see the source Document name and passage when the Agent shows them, so that I can trust the answer.
20. As a Visitor, I want my Conversation still there if I reload the page or navigate within the site within 24 hours, so that I don't lose context.
21. As a Visitor, I want to start a new Conversation, so that I can change topic cleanly.
22. As a Visitor, I want to end the chat, so that I can close it when I'm done.
23. As a Visitor, I want a polite, on-brand message instead of an error when the Agent is temporarily unavailable, so that I'm not confused.
24. As a Visitor, I want a friendly message if an Agent has been retired, so that I know it's gone rather than broken.
25. As a Visitor using a keyboard, I want to open, use and close the widget with focus trapped inside while it's open and returned to the launcher afterwards, so that I can use it without a mouse.
26. As a Visitor using a screen reader, I want new replies announced politely once complete, and controls properly labelled, so that I can follow the Conversation.
27. As a Visitor, I want the widget to respect reduced-motion preferences, so that animations don't bother me.
28. As a Visitor on a phone, I want the widget to fill the screen comfortably when open, so that chatting on mobile is easy.
29. As a host-site developer, I want the embed script small, asynchronous and free of global side effects beyond its iframe, so that it doesn't slow or break our page.
30. As a host-site developer, I want the widget's styles and scripts isolated from my page, so that neither breaks the other.
31. As an Owner, I want the Agent to show an alert badge in the Studio when its budget is exhausted or limits are being hit heavily, so that I can react.
32. As an Owner, I want an email when an Agent's Token Budget is exhausted, so that I find out without watching the Studio.
33. As an Owner, I want the Token Budget to reset at midnight UTC, so that the Agent recovers automatically.
34. As an Owner, I want the Playground excluded from the Token Budget, so that testing can never take the live Agent offline.
35. As an Owner, I want a page that isn't on the Allowed Origins list unable to show the Agent, so that our Agent and our budget can't be borrowed.

## Implementation Decisions

- **Embed loader.** A tiny standalone script, with no framework and a size budget enforced in CI. It reads `data-agent` (public ID), optional `data-launcher` (bubble or inline) and `data-target` (selector for inline). It creates the iframe pointing at the widget shell route. In bubble mode it also renders a launcher button inside the iframe and resizes the iframe via `postMessage` (open/closed sizes), validating the message origin both ways.
- **Widget shell route** (API, routed through CloudFront per ADR-0011). Given the public ID, the API:
  - resolves the Agent, refusing archived Agents or Agents with no Live Version with the "no longer available" shell;
  - computes `Content-Security-Policy: frame-ancestors` from the Allowed Origins;
  - inlines the resolved Theme as CSS custom properties (spec 02's resolution function with the per-Agent override);
  - inlines the public Experience fields from the Live Version (name, avatar, greeting, starter questions, UI text, citation setting, rating prompt timing);
  - issues a short-lived bootstrap token bound to the Agent;
  - references the widget bundle from static storage.
- **Widget app.** React, using the shared UI primitives that read Theme tokens as CSS variables (the same components the Studio's Theme preview renders). Keyboard focus management, a live region, reduced-motion handling, and a mobile full-screen layout.
- **Conversation tokens.** The bootstrap token is exchanged for a Conversation token: signed and opaque, bound to Agent and Conversation, expiring 24 hours after last activity, sliding. Only its hash is stored. The widget stores it in iframe local storage, which browsers partition per top-level site, giving the 24-hour resume. Resuming fetches the Conversation's Messages.
- **Widget API.** Create Conversation, get Conversation, send message (SSE stream: token, citation, done, unavailable and error events), end Conversation. Requests are authenticated only by the Conversation token. CORS is unnecessary because the iframe shares the API's origin (ADR-0011).
- **Admission control module.** One operation, `admit(agent, conversation token, client IP)`, returning allowed or a refusal reason. It checks:
  - Redis sliding-window counters per token and per IP, with limits taken from Operational Settings;
  - the Token Budget, as a Redis counter keyed by Agent and UTC date, incremented with actual usage after each reply.
  A refusal returns the unavailable event. The first refusal per Agent per day because of the budget triggers the alert flag and an Owner email through the mailer port (deduplicated). Client IP is taken from CloudFront and ALB forwarding headers, with trusted-proxy configuration.
- **Serving.** Visitor messages go through admission, then the runtime from spec 04 with the Live Version's AgentConfig and pinned Instructions (spec 05). The Message records the Agent Version that produced it. Each reply uses whichever Version is Live at the time it's generated (plan section 3).
- **Operational Settings model.** Per Agent: Allowed Origins list, rate limits, Token Budget, unavailable text, and the Theme override (colours and avatar). Edited through their own endpoints and not part of AgentConfig (ADR-0009). All changes go through the audit module. The Theme override is Owner-only, consistent with the Theme.
- **Budget reset.** Counters are keyed by UTC date, so reset happens naturally. A Beat task clears the alert flags at midnight UTC.
- **Studio UI.** Agent "Embed" tab (snippet with copy button, layout options, a live preview of the widget, Allowed Origins editor), Operational Settings form, usage-against-budget meter, alert badge on the Agent list and Agent page.
- **Seed host page.** A static demo host page in the repo, served by `docker compose` on a separate port, so cross-origin embedding is exercised for real locally.

## Testing Decisions

- **Good tests** load the widget the way a host page would and assert what a Visitor sees and what the API refuses. They don't assert on internal token formats beyond "tampered or expired tokens are refused".
- **API seam:**
  - the shell route's CSP header for various Allowed Origins sets, including wildcards and localhost;
  - archived and not-Live Agents get the unavailable shell;
  - bootstrap → Conversation token exchange; tampered, expired and cross-Agent tokens refused;
  - resume within 24 hours and refused after (controllable clock);
  - send message streams through the runtime fake with the Live Version's config and Instructions;
  - Message attribution to the Live Version, which changes immediately after a revert mid-Conversation;
  - Operational Settings changes apply on the next request and are audited.
- **Admission control** is tested through its interface against real Redis:
  - per-token and per-IP limits with window rollover (controllable clock);
  - budget exhaustion after recorded usage, the unavailable outcome, the alert flag, a single deduplicated Owner email in the outbox;
  - midnight UTC reset;
  - Playground excluded.
- **Trusted-proxy IP extraction:** a table test of header combinations.
- **Frontend, network seam (widget):** greeting and starter questions; streaming render; citations expand; unavailable and retired states; resume shows previous Messages; new and end Conversation; Theme tokens applied as CSS variables; keyboard focus trap and return; live-region announcements; reduced motion.
- **Frontend, network seam (Studio):** snippet generation for both layouts, Allowed Origins validation messages, budget meter, alert badge.
- **End-to-end (Playwright):**
  - the seed host page (allowed origin) embeds the widget, a Visitor chats and sees a streamed reply;
  - a host page on a disallowed origin is blocked from framing (asserted through the browser's refusal);
  - exhausting a tiny budget shows the unavailable message;
  - axe reports no WCAG 2.2 AA violations on the open widget in light and dark mode.
- **Embed loader:** unit tests in a DOM environment for attribute parsing, iframe creation, `postMessage` origin validation and resizing. A CI check enforces the size budget.
- **Prior art:** spec 04 runtime fakes, spec 05 Live Version resolution, spec 02 Theme resolution.

## Out of Scope

- Identified Visitors or Organisation-signed user identities.
- Defences against non-browser clients beyond rate limits and budgets (ADR-0004 explains why).
- Collecting feedback and ratings (spec 07). The widget leaves room for them.
- Guardrail enforcement (spec 08). Refusal events are already part of the stream contract.
- Full i18n bundles. UI text overrides only.

## Further Notes

- The "embedding from a disallowed origin is blocked" end-to-end test is a strong demo. Make it visible in the seed showcase (spec 10).
- Third-party storage partitioning is relied on deliberately. If a browser blocks iframe storage completely, the widget silently degrades to no resume.
