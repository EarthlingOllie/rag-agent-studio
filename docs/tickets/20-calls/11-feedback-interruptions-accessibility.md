# 11: Feedback, interruptions and accessibility

**Ticket:** `20-11` · **Spec:** [Calls](../../specs/20-calls-spec.md)

**What to build:** A Call is as reviewable and as accessible as the chat: thumbs on spoken replies, a rating prompt that waits, interrupted replies marked, and full keyboard and screen-reader use.

**Blocked by:**
- `20-04`

**Status:** done

- [x] Spoken replies take Message Feedback in the log, during and after the Call
- [x] The rating prompt waits until the Call ends, then follows its usual rule
- [x] When the Visitor talks over a reply the widget tells the API; the Agent Message is marked interrupted and keeps its whole text
- [x] The Reply announcement is silent during a Call; the Call's start, its end and the reason it ended are announced politely
- [x] The choice screen, Mute and End call are labelled and reachable by keyboard, focus stays inside the open widget, and reduced motion is respected in the speaking and listening states
- [x] Axe reports no WCAG 2.2 AA violations on the choice screen and the Call view, in light and dark mode
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
