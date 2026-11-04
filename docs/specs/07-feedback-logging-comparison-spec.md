# Spec 07: Feedback, logging and comparison

## Problem Statement

Publishing a new Version is only useful if the team can tell whether it was better. Today there's no way to know whether Visitors are satisfied, what each Version costs to run, or which answers went wrong and why. Raw token counts and anecdotes aren't enough. Teams need per-Version metrics they can trust, with honest uncertainty when samples are small, and the ability to drill into individual Conversations to see exactly what happened. At the same time, Visitors type personal information into chats, so the Organisation needs Message text to expire on a schedule it controls without losing the aggregate history.

## Solution

Visitors can give Message Feedback (thumbs up or down with an optional comment) on any Agent reply, and a Conversation Rating (1–5). The rating is asked for after a configurable number of replies and again on "End chat", and can be changed. Every Agent Message already carries a full Trace (spec 04).

This slice adds:
- **Conversations area:** browse, filter and drill into Conversations, with Traces and feedback inline.
- **Analytics:** each Agent Version's volume, tokens, cost, thumbs-up rate (with a Wilson 95% interval and sample size), mean rating, Guardrail block rate, fallback rate and latency.
- **Comparison:** any two Versions side by side, and a time series marked where the Live Version changed.
- **Exclusions and retention:** Playground Conversations are excluded. A Retention Window purge removes Message text after the Organisation's chosen period while aggregates stay intact. Deleted Documents leave tombstones in Traces.

## User Stories

1. As a Visitor, I want to give a thumbs up or down on any Agent reply, so that I can say whether it helped.
2. As a Visitor, I want to add an optional comment when I give a thumbs down, so that I can explain what was wrong.
3. As a Visitor, I want to change or remove my thumbs on a reply, so that I can correct a misclick.
4. As a Visitor, I want an unobtrusive prompt to rate the Conversation after a few replies, so that I can give overall feedback without being nagged.
5. As a Visitor, I want to be asked for a rating when I end the chat if I haven't rated yet, so that I can rate at a natural moment.
6. As a Visitor, I want to dismiss the rating prompt, and have it not reappear in that Conversation unless I end the chat, so that it doesn't get in my way.
7. As a Visitor, I want to change my Conversation Rating later, so that my rating reflects how the Conversation ended up.
8. As a Visitor using assistive technology, I want the feedback controls and rating prompt fully accessible, so that I can give feedback too.
9. As an Editor, I want a Conversations list per Agent and per Project, filterable by date, Version, feedback, rating, Guardrail outcome and Playground, so that I can find interesting Conversations.
10. As an Editor, I want to open a Conversation and read it with each reply's feedback, comment and Trace inline, so that I understand what happened.
11. As an Editor, I want each Trace to show the retrieved Chunks with scores and whether they were cited, linked to the Document viewer, so that I can diagnose a bad answer.
12. As an Editor, I want Traces whose Document was later deleted to show "Chunk from deleted Document <name>" instead of breaking, so that history stays readable.
13. As an Editor, I want to see each Version's number of Conversations and Messages, so that I know how much evidence there is.
14. As an Editor, I want mean and p95 tokens per reply per Version, so that I can see whether a change made answers bloated.
15. As an Editor, I want cost per Conversation per Version, using prices fixed at the time of each reply, so that cost comparisons are accurate even after prices change.
16. As an Editor, I want the thumbs-up rate per Version with a 95% confidence interval and sample size, so that three lucky votes don't look like a winner.
17. As an Editor, I want the mean Conversation Rating per Version with its count, so that I can compare overall satisfaction.
18. As an Editor, I want each Version's Guardrail block rate and fallback ("I don't know") rate, so that I can see safety and coverage effects.
19. As an Editor, I want p95 time-to-first-token and total latency per Version, so that I can spot slower models or prompts.
20. As an Editor, I want to pick any two Versions of an Agent and see all metrics side by side, with differences highlighted, so that I can decide which is better.
21. As an Editor, I want to see the configuration diff between the two Versions next to the metrics, so that I can connect changes to outcomes.
22. As an Editor, I want a time series of key metrics with markers where the Live Version changed, so that I can see the effect of each release over time.
23. As an Editor, I want to choose the date range, so that I can focus on a relevant period.
24. As an Editor, I want Playground Conversations excluded from all analytics, so that testing doesn't skew results.
25. As an Editor, I want a warning that Knowledge Base changes during a comparison window may confound results, so that I interpret comparisons correctly.
26. As an Editor, I want to export a Version comparison as CSV, so that I can share it.
27. As an Owner, I want to set the Organisation's Retention Window (default 90 days), so that we don't keep Visitor Message text longer than needed.
28. As an Owner, I want Message text and feedback comments older than the Retention Window purged automatically, so that personal data expires without manual work.
29. As an Owner, I want aggregate metrics kept after a purge, so that long-term comparisons still work.
30. As an Owner, I want to delete a specific Conversation on request, so that we can honour a Visitor's deletion request.
31. As an Owner, I want the purge to apply to archived Agents and Projects too, so that archiving isn't a way around retention.
32. As an Owner, I want Retention Window changes and manual Conversation deletions recorded as Audit Events, so that data handling is accountable.
33. As an Owner, I want Organisation-wide cost per Project and per Agent for a period, including Playground usage, so that I know what we're spending.

## Implementation Decisions

- **Feedback module.**
  - Message Feedback: one per Agent Message (thumbs up or down, optional comment). Upserting replaces it, and removing deletes it.
  - Conversation Rating: one current value per Conversation, plus an append-only change log.
  - Widget endpoints are authenticated by the Conversation token (spec 06). A Visitor can only give feedback on Messages in their own Conversation.
  - When the rating prompt is shown is decided client-side from the Live Version's Experience setting. The server stores whether the prompt was dismissed, so it isn't shown again in that Conversation.
- **Attribution.**
  - Message Feedback belongs to the Agent Version of the Message it's on.
  - A Conversation Rating belongs to the Version of the last Agent Message before the rating (or the change).
  - Both are calculated when written and stored, so later reverts don't move them.
- **Message record (completing spec 04's).** Provider, model, Agent Version or Draft marker, Instructions Version or Draft marker (Playground), input, output and cached tokens, cost (frozen), time to first token, total latency, fallback-used flag, Guardrail outcomes (list of layer, verdict, reason; populated by spec 08), purged-at.
- **Message retrievals:** Chunk ID (nullable), Document ID (nullable), a Document-name snapshot (the tombstone), score, rank, cited flag, excluded reason. When a Document is deleted, the IDs are set to null and the name snapshot is kept.
- **Analytics module.** A deep module with a small query interface:
  - `version_metrics(agent, versions, date range)`;
  - `time_series(agent, metric, date range, granularity)` with Live History markers;
  - `org_cost(period, group by Project or Agent)`.
  It reads from:
  - `usage_daily` rollups (per Agent Version per UTC day: Conversations, Messages, token sums, a token histogram for percentiles, cost, thumbs up and down counts, rating sum and count, block count, fallback count, latency histograms);
  - raw tables for the current partial day.

  Percentiles come from fixed-bucket histograms, which are accurate enough and can be merged across days. Wilson intervals are calculated at query time from the counts. A rollup Beat task runs hourly for the current day and finalises the previous day. Rollups are idempotent (recomputed per day).
- **Exclusions.** Playground Messages never go into the Visitor rollups. Org cost includes them in a separate column.
- **Retention.** The Organisation setting is Retention Window days (default 90). A daily Beat purge task clears Message content and feedback comments older than the window, sets purged-at, and leaves every numeric and attribution field in place. Rollups are computed before purging. Manual Conversation deletion removes its Messages' text and comments immediately, through the same purge path, and is audited.
- **API.**
  - Widget: feedback and rating endpoints.
  - Studio: Conversations list with filters, Conversation detail with Traces and feedback, Version metrics, comparison, time series, CSV export, org cost, Retention Window setting, Conversation deletion.
- **Studio UI.**
  - Conversations tab (table plus detail with an inline Trace drawer).
  - Analytics tab:
    - Version picker;
    - KPI cards with intervals and sample sizes;
    - comparison table with a highlighted difference and a config diff (reusing spec 05's diff);
    - a Recharts time series with Live History markers;
    - a confounder note when Documents changed in the window.
  - Organisation cost page.
  - Retention setting in Organisation settings.
- **Widget UI.** Thumbs controls on each Agent reply with an optional comment popover; rating prompt card (1–5) after the Nth reply and on end; changing a rating.

## Testing Decisions

- **Good tests** generate Conversations through the widget API using the runtime fake, add feedback, run the rollup task, and assert on the analytics endpoints' numbers. They don't assert on rollup table contents directly.
- **API seam:**
  - feedback upsert, change and remove; feedback only allowed on your own Conversation's Messages;
  - rating, change and change log;
  - attribution across a mid-Conversation revert (feedback goes to the Message's Version; the rating goes to the last reply's Version);
  - the Conversations list filters;
  - Trace detail including tombstones after deleting a Document;
  - Playground exclusion.
- **Analytics** is tested through its interface with a generated fixture set, including a known small-sample case. Assertions:
  - Wilson bounds against reference values;
  - percentiles from histograms within tolerance of the exact values;
  - cost uses frozen values after a price override changes;
  - time-series markers match the Live History;
  - rollup idempotence (run twice gives the same results);
  - the current partial day is included.
- **Retention:** with the controllable clock, Messages older than the window lose their text and comments while the metrics endpoints return identical numbers before and after the purge; archived Agents are purged; manual deletion; Audit Events.
- **Frontend, network seam:**
  - widget: thumbs and comment, rating prompt timing (after N, on end, dismissed), changing a rating, accessibility of the controls;
  - Studio: Conversations filters, Trace drawer with tombstone, KPI cards with intervals and the small-sample visual treatment, comparison highlighting, time series with markers, CSV export, Retention setting.
- **End-to-end:** a Visitor chats on the seed host page, gives a thumbs down with a comment and a 2-star rating; the Editor finds the Conversation, opens the Trace, and sees the feedback reflected in the Version's metrics after the rollup task runs.
- **Prior art:** spec 06 widget fixtures, spec 05 Live History and diff, spec 02 cost function.

## Out of Scope

- Inferred sentiment analysis of Visitor messages (future).
- Statistical significance testing beyond confidence intervals, and A/B traffic splitting.
- Real-time dashboards (hourly rollups plus the live partial day is enough).
- Exporting raw Conversations in bulk.

## Further Notes

- Showing the Wilson interval and sample size prominently is a deliberate product choice. Keep the small-sample visual treatment (muted, with a "low confidence" label) when redesigning.
- Rollups must happen before purges. The purge task checks the rollup for the affected days is final before clearing text.
