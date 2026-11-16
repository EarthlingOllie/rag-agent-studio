# 04: Live Verdicts in the Conversations viewer

**Ticket:** `15-04` · **Spec:** [Live evaluation](../../specs/15-live-evaluation-spec.md)

**What to build:** An Editor filters the Conversations viewer to failed Live Verdicts, sees which Conversations have the most failed replies, and adds a failed reply to the Evaluation Set.

**Blocked by:**
- [15-01: Live Verdict tracer: sample a reply and judge it](01-live-verdict-tracer.md)

**Status:** ready-for-agent

- [ ] The Conversations viewer list accepts a Live Verdict filter (`passed`, `failed`, `error`, `not_judged`), combinable with the existing filters
- [ ] Each listed Conversation shows how many of its replies failed their Live Verdict
- [ ] The Studio adds the filter and the count to the Conversations viewer and each Agent's Conversations view
- [ ] "Add to Evaluation Set" works from a reply with a failed Live Verdict, unchanged from spec 14 (case keeps no link to the Conversation)
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
