# 07: Call limits

**Ticket:** `20-07` · **Spec:** [Calls](../../specs/20-calls-spec.md)

**What to build:** An Editor sets a Maximum Call length and a daily Call minutes budget and sees today's minutes against it; Calls that pass a limit are ended or refused, and an open line can't be abused.

**Blocked by:**
- `20-04`

**Status:** ready-for-agent

- [ ] Operational Settings gain Maximum Call length (10 minutes by default) and Call minutes budget (60 per UTC date by default), audited like the rest
- [ ] A Call that reaches the Maximum Call length is ended by the platform, and the widget returns to the chat saying why
- [ ] Ending a Call adds its minutes, rounded up and timed by the platform's clock, to the Agent's counter for the UTC date; once the budget is spent, starting a Call is refused with the Unavailable text and the Visitor is offered messaging
- [ ] The first refusal of a day raises the Agent's Budget alert and emails the Owners once; a new UTC date starts a new counter and clears the alert
- [ ] Starting a Call is refused while the Conversation has one open, or while the client IP has the platform's cap of concurrent Calls (two)
- [ ] A Beat task ends Calls with no turn for 60 seconds, which also closes Calls whose browser vanished; ending a Conversation ends its Call
- [ ] Embed & limits shows the two limits and a Call minutes meter beside the Token Budget meter; the Agents list badges the alert
- [ ] Playground use doesn't count
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
