# Evidence: ticket 07-02, Message Feedback

Branch `ticket/07-02-message-feedback`, from `origin/candidate` at `2090bf5` (07-01, Conversations viewer, merged). The claim commit, the first on the branch, set Status `in-progress`. Every check below was run from a **fresh clone of the pushed branch** (a clean checkout), one at a time; each log's first line names the commit.

**Status: done.** Every criterion is met and evidenced below. Gaps and judgement calls are listed at the end.

## What was built

- **Feedback module** (`backend/app/feedback/`, new):
  - `models.py`: table `message_feedback` (migration `0031_message_feedback`): one row per Agent Message (unique `message_id`, cascades with the Message), `rating` (`up`/`down`), optional `comment` (≤1000 characters), `agent_version_id` copied from the Message when written, `updated_at` from the app's Clock.
  - `service.py`: `give` (upsert: giving again replaces rating and comment), `remove` (delete; removing nothing is harmless), `feedback_on` (by Message ID). Both writes first find the reply **inside the token's Conversation** and only among Agent Messages, else `ReplyNotFoundError`.
  - `api.py`: widget routes under the widget API, authenticated by the Conversation token (`Authorization: Bearer …`):
    - `PUT /api/widget/agents/{public_id}/messages/{message_id}/feedback` (`giveMessageFeedback`), body `{rating: "up"|"down", comment?: string|null}` (blank comment counts as none) → `{rating, comment}`;
    - `DELETE` same path (`removeMessageFeedback`) → 204.
    - 401 for a tampered, ended, expired or other-Agent token (same rules as the other widget routes, through a new `embed.service.visitor_conversation`); 404 "There is no such reply in this chat." for any Message not an Agent reply in the token's own Conversation; 422 for a bad body.
- **Widget resume** (`GET /api/widget/agents/{public_id}/conversation`): each Message now carries its `id` and, for a reply, the Visitor's `feedback` (`{rating, comment}` or null), so a Visitor who comes back sees and can change it.
- **Conversations viewer API** (`backend/app/conversations/`): the list takes `feedback=up|down|any|none` (a reply with a thumbs up / down, any feedback, none) and each row has `thumbs_up` and `thumbs_down` counts; the detail's Messages carry `feedback` `{rating, comment, agent_version_number, updated_at}`, the Version number read from the stored attribution.
- **Widget** (`frontend/apps/widget/src/Feedback.tsx`, new; `Widget.tsx`, `chat.ts`, `styles.ts`): each finished Agent reply shows a "Was this reply helpful?" group with **Helpful** / **Not helpful** toggle buttons (`aria-pressed`); pressing the chosen one again removes the feedback; once a thumb is chosen, **Add a comment** / **Edit comment** opens a "Comment (optional)" box (max 1000) with Save comment / Cancel; the saved comment is shown in quotes. Status messages ("Thanks for your feedback.", "Feedback removed.") and errors ("Your feedback couldn't be saved. Please try again.", or the expired-chat message) are announced. `ask` now resolves with the stream's `message_id`, which the reply keeps.
- **Studio** (`ConversationsTab.tsx`, `conversations.ts`): a **Feedback** column ("1 up · 2 down" or "None"), a **Feedback** filter (Any or none / Thumbs up / Thumbs down / With feedback / Without feedback) kept in the URL, and on the Conversation page each reply's "Visitor feedback" group: "Thumbs up|down · for Agent Version vN · <time>" and the comment, or "No feedback" in a Visitor Conversation.
- **Generated API client** regenerated. **Glossary**: **Message Feedback** and **Conversations viewer** updated.

## Test seams

The [shared test seams](../../../specs/README.md#shared-test-seams) and the spec's Testing Decisions. Not confirmed with a human (none is reachable in this run); they are the ones the spec names.

- **API seam:** `backend/tests/integration/test_message_feedback.py` (13 tests, 17 cases). Visitors use clients with no Studio session and go through the widget API; replies come from the `FunctionModel`; the controllable clock drives expiry and timestamps. Assertions are on HTTP responses (widget resume, Conversations list and detail) only.
- `test_widget_resume.py` now also checks each resumed Message's `id` (matching the stream's `message_id`) and `feedback`; `test_openapi.py` lists the two new operations.
- **Network seam:** `frontend/apps/widget/src/Feedback.test.tsx` (13 tests, MSW) and `frontend/apps/studio/src/projects/ConversationsTab.test.tsx` (6 new tests, existing ones updated for the Feedback column).
- **End-to-end seam:** `frontend/e2e/tests/message-feedback.spec.ts`, Playwright against the compose stack with the fake chat model, with axe on the host page (widget iframe included) and the Studio.

## Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | The widget offers thumbs plus an optional comment, which can be changed or removed | **API:** `test_a_visitor_gives_a_thumbs_up_and_sees_it_when_they_come_back`; `test_a_visitor_changes_their_thumbs_and_adds_a_comment` (up → down with a trimmed comment → giving again without a comment drops it → a blank comment is none); `test_a_visitor_removes_their_feedback` (204, gone on resume, removing again harmless, can give afresh); `test_each_reply_has_its_own_feedback`; `test_bad_feedback_is_refused` (no rating, unknown rating, null, 1001-character or non-string comment: 422, nothing stored); `test_a_comment_of_the_longest_length_is_kept` (1000).<br>**Widget:** `Feedback.test.tsx`: thumbs up (aria-pressed, status, the exact PUT); thumbs down + comment, edit (prefilled, Cancel keeps), switching thumbs keeps the comment, clearing the comment; pressing the chosen thumb removes it (DELETE); each reply its own; resumed feedback shown and changeable; no thumbs while streaming; refusals (404, 401 expired), network failure and refused comment are undone and announced; an expired chat sends nothing; `maxlength=1000`.<br>**E2E:** the Visitor on the demo host page gives Helpful, switches to Not helpful, adds a comment, reloads and still sees both; axe clean. |
| 2 | Feedback is only allowed on Messages in the Visitor's own Conversation | **API:** `test_feedback_is_only_allowed_on_replies_in_the_visitors_own_conversation`: another Visitor's reply on the same Agent, the Visitor's own question, the Visitor's reply in a Conversation with another Agent, a Playground reply and an unknown ID are all 404 for both PUT and DELETE, and the other Visitor's reply is untouched. `test_feedback_needs_a_valid_conversation_token_for_that_agent`: tampered token, garbage, another Agent's path, an ended Conversation's token, no header, a non-Bearer scheme → 401. `test_feedback_is_refused_once_the_conversation_token_has_expired` (24 h + 1 s → 401). |
| 3 | Feedback is attributed to the Message's Version, stored when written | **API:** `test_feedback_belongs_to_the_replys_version_whatever_is_live_later`: v1 answers, v2 is published and answers, then the Agent is **reverted** to v1; feedback given afterwards on v2's reply counts for v2 and on v1's reply for v1 (`agent_version_number` in the Conversations detail, with the Clock's `updated_at`); a further publish leaves both as they were. The Version is copied into `message_feedback.agent_version_id` at write time (`app/feedback/service.py`).<br>**Studio:** "an Editor reads each reply's Visitor feedback, with its comment and the Version it counts for" ("for Agent Version v1/v2"); the Draft case ("for the Draft").<br>**E2E:** the Editor sees "Thumbs down · for Agent Version v1". |
| 4 | The viewer shows feedback and can filter by it | **API:** `test_the_list_shows_each_conversations_thumbs_and_filters_by_feedback` (per-row `thumbs_up`/`thumbs_down`; `feedback=up`, `down`, `any`, `none`, combined with `playground=false`; an unknown value is 422); `test_removed_feedback_leaves_the_viewer`; the detail's `feedback` in the attribution test above.<br>**Studio:** "the list shows each Conversation's thumbs and is filtered by feedback" (column text, the five options, the query sent, back to Any or none drops it); "a feedback filter in the URL is kept"; "an unknown feedback filter in the URL is ignored"; the detail tests (thumb, Version, time, comment as a blockquote; "No feedback").<br>**E2E:** the list row shows "1 down"; Thumbs up finds nothing, Thumbs down finds the Conversation and puts `feedback=down` in the URL; the Conversation page shows the feedback and comment; axe clean. |
| 5 | Tests cover the new behaviour at the highest seam; 100% line and branch coverage holds | Seams as above. Backend: RESULT_BACKEND. Frontend: RESULT_FRONTEND. No coverage exclusions or pragmas added. |
| 6 | New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed | `GLOSSARY.md`: **Message Feedback** now says one per Agent Message, in the Visitor's own Conversation, the 1000-character comment, change (replace) and remove, and the Version attribution stored when written; **Conversations viewer** gains the feedback filter, the thumbs counts and the feedback on each reply. No ADR decision changed. |

## Results

RESULTS_TABLE

## Gaps and judgement calls

- **Seams not confirmed with a human.** The TDD skill asks for the seams to be agreed first; no human is reachable, so the spec's own seams were used.
- **Feedback on a retired Agent's replies** is still accepted while the Conversation token is valid (the same rule as ending a Conversation); the widget itself shows "no longer available" by then, so Visitors can't reach it. Best guess: refusing would only lose data.
- **Feedback doesn't count as Conversation activity**, so it doesn't slide the token's 24-hour window (only questions and resumes do).
- **Giving feedback replaces it whole**: a PUT without a comment clears the comment. The widget always sends the current comment when switching thumbs, so a Visitor's comment survives a thumb change.
- **Removing** the thumbs removes the comment with it (one record per Message, as the spec says).
- **The `none` filter** includes Playground Conversations (they have no feedback); combine with Show = Visitors only to see unrated Visitor Conversations.
- **Rollups and Version KPIs** (thumbs-up rate, Wilson interval) are ticket 07-04; this ticket stores the attribution they will read (`message_feedback.agent_version_id`, indexed).
- **Migration numbering:** `0031_message_feedback` follows `0030_agent_theme_override` on candidate; tickets merging in parallel that also add a `0031` must re-chain `down_revision` at merge time.
- **Small edits outside the new module:** `embed/service.py` (resume returns IDs and feedback; a public `visitor_conversation`), `embed/api.py` (`WidgetMessageOut` gains `id` and `feedback`), and `ConversationsTab` re-filters the URL search because the router passes unknown parent search values through.
