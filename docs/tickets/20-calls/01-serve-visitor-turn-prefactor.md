# 01: Prefactor: serve a Visitor turn from one place

**Ticket:** `20-01` · **Spec:** [Calls](../../specs/20-calls-spec.md)

**What to build:** No behaviour changes: the widget's message route hands each Visitor turn to one serving function (admission, Live Version resolution, the runtime, saving, usage and budget counters) that yields the runtime's events, so the turn endpoint of ticket 20-04 can reuse it.

**Blocked by:**
- None

**Status:** ready-for-agent

- [ ] One serving function takes the Agent, the Conversation, the Visitor's words and the client IP, and yields the runtime's events and admission refusals; the widget's message route only turns them into Server-Sent Events
- [ ] It covers everything the route does today: rate limits and the Token Budget, the retired-Agent outcome, the Live Version and its pinned Instructions, Message attribution, the Trace, Cost, usage and budget counters, Live sampling
- [ ] The widget API's responses and event stream are unchanged; the existing API-seam and widget tests pass without edits to their assertions
- [ ] The generated API client is unchanged
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
