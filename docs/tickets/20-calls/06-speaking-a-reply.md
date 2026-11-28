# 06: Speaking a reply well

**Ticket:** `20-06` · **Spec:** [Calls](../../specs/20-calls-spec.md)

**What to build:** A spoken reply sounds right: no formatting or citation markers, the Searching status while the Agent searches, and a spoken refusal, replacement or Unavailable text when a reply doesn't go to plan.

**Blocked by:**
- `20-04`

**Status:** done

- [x] Text streamed to the voice layer has Markdown and citation labels stripped; the saved Message and the Conversation log keep the full text with its sources
- [x] When an Agentic reply starts a Search, the Searching status (or the Agent's UI text override) is spoken once per reply as a buffer phrase
- [x] Text that could still be retracted is held back from speech until it can't be, so nothing spoken is taken back; the Fallback Text is spoken when the Searches found nothing
- [x] A Guardrail block speaks the Agent's refusal text and the Call goes on
- [x] A Canary trip mid-reply stops the stream and speaks the replacement text
- [x] An unavailable outcome (rate limit, spent Token Budget, provider failure, no effective model, the Agent retired) speaks the Unavailable text, ends the Call and returns the Visitor to messaging
- [x] Spoken replies add their tokens to the Token Budget and count toward the rate limits like typed ones
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes (no new Studio UI: the widget only returns the Visitor to messaging, with its existing alert)
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
