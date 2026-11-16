# Spec 15: Live evaluation

**Status:** ready-for-agent · **Builds on:** [Spec 06](./06-embed-widget-operational-settings-spec.md), [Spec 07](./07-feedback-logging-comparison-spec.md), [Spec 14](./14-evaluation-loop-spec.md) · **Decisions:** [ADR-0009](../adr/0009-operational-settings-outside-versions.md), [ADR-0016](../adr/0016-evaluation-cases-outlive-retention.md)

## Problem Statement

Spec 14 lets an Editor check a change before Publishing, but only against the questions in the Agent's Evaluation Set. Once a Version is Live, the Studio only knows how it is doing from what Visitors choose to say:

- **Visitors rarely vote.** Thumbs and Conversation Ratings arrive on a small share of replies. Most Versions sit in Low sample for days, and the replies nobody voted on (most of them) are never assessed at all.
- **Votes measure mood, not quality.** A Visitor gives a thumbs-down to a correct answer they didn't like, and a thumbs-up to a confident answer that made something up. Nothing checks whether a Live reply is grounded in its Citations.
- **A bad Publish is found late.** An Evaluation Set covers the questions Editors thought of. A Version that breaks the questions they didn't think of is only noticed when enough thumbs go down, if they do.
- **Nobody watches all the time.** The Block rate alert tells Owners when an attack starts. Nothing tells them when a newly Live Version is answering worse than the one before it.
- **Spend has no ceiling.** Spec 14's Runs are started by hand after seeing their estimated Cost. Judging live traffic happens without anyone pressing a button, so it needs a limit an Owner sets in advance.

## Solution

The Evaluation Model judges a sample of each Agent's Visitor replies in the background, and the Studio turns those judgements into a quality number per Version, an alert, and a budget.

- **Sample.** Each Agent's Operational Settings gain a **Live sample rate** (0% by default). When a Visitor reply finishes, it is chosen at random with that probability. Replies the input Guardrail blocked and Fallback Text replies are never chosen.
- **Judge.** A chosen reply gets a **Live Verdict** in the background: the Evaluation Model, given what the Agent saw (its Remembered turns, the question and the Chunks it was given) and the reply with its Citations, says whether the reply is **grounded** and whether it **answers the question**, each pass or fail with a one-sentence reason. The Visitor never waits for it.
- **Measure.** Each Version gets a **Live score**: the share of its Live Verdicts that passed. It is a Version KPI with its Wilson interval, a row in the Version comparison and a Time series metric.
- **Alert.** Once a newly Live Version has 30 Live Verdicts, the hourly check compares its Live score with the previous Live Version's. A clear drop raises the **Live score drop alert**: a badge and one email to Owners.
- **Cap spend.** Owners set a monthly **Evaluation budget** in US dollars. Without one, sampling can't be turned on. When the month's spend reaches it, sampling pauses across the Organisation until the 1st and Owners are emailed once.
- **Feed the loop.** Live Verdicts show in each reply's Trace, the Conversations viewer filters by them, and a failed reply goes into the Evaluation Set with spec 14's "Add to Evaluation Set".
- **The demo tells the story.** The HR helper's v1 and v2 have Live Verdicts, so v2's drop shows in the Version comparison and the Time series.

## User Stories

### Sampling

1. As an Editor, I want to set an Agent's Live sample rate from 0% to 100% in its Operational Settings, so that I choose how much of its traffic is judged.
2. As an Editor, I want the rate to apply at once without Publishing, so that I can turn judging up while watching a new Version and down afterwards.
3. As an Owner, I want changes to the Live sample rate recorded as Audit Events, so that a jump in evaluation spend can be traced.
4. As an Owner, I want the Live sample rate to be 0% by default, so that nothing is spent until someone chooses to.
5. As an Editor, I want the Live sample rate field disabled with an explanation while the Organisation has no Evaluation budget, so that I know why I can't turn it on.
6. As an Editor, I want replies chosen at random, so that the Live score isn't biased towards any kind of question.
7. As an Editor, I want replies the input Guardrail blocked left out of the sample, so that the budget isn't spent judging the Refusal text.
8. As an Editor, I want Fallback Text replies left out of the sample, so that the Live score measures the answers the Agent actually gave.
9. As an Editor, I want Playground replies never sampled, so that my own testing doesn't count as Visitor quality.
10. As a Visitor, I want my reply delivered without waiting for any judging, so that evaluation never slows the chat.

### Live Verdicts

11. As an Editor, I want each sampled reply judged on whether every claim is supported by its Citations, so that I catch Live replies that make things up.
12. As an Editor, I want each sampled reply judged on whether it answers the question, so that I catch grounded replies that miss the point.
13. As an Editor, I want the judge to see the Remembered turns, so that a follow-up such as "what about part-timers?" is judged in context.
14. As an Editor, I want the judge to see the Chunks the Agent was given and which ones it cited, so that grounding is judged against the same material.
15. As an Editor, I want the judge never to see the system prompt, so that it judges the answer rather than the instructions.
16. As an Editor, I want each check's one-sentence reason, so that I can tell why a reply failed.
17. As an Editor, I want a reply to pass only when both checks pass, so that the Live score means "grounded and on point".
18. As an Editor, I want a reply the Evaluation Model couldn't judge marked Error and left out of the Live score, so that a provider outage doesn't look like a quality drop.
19. As an Editor, I want a reply whose text was Purged before it was judged skipped, so that nothing is judged without its text.
20. As an Editor, I want the judge to treat the reply, the question and the Chunks as data, never as instructions, so that a prompt-injected reply can't vote for itself.
21. As an Owner, I want Live Verdicts judged by the Organisation's Evaluation Model, so that live and Evaluation Run judgements are comparable.

### Seeing Live Verdicts

22. As an Editor, I want a reply's Live Verdict in its Trace, with both checks and their reasons, so that I see it where I already investigate replies.
23. As an Editor, I want a "Not judged" state in the Trace for replies that weren't sampled, so that I can tell unsampled from pending.
24. As an Editor, I want to filter the Conversations viewer by Live Verdict (passed, failed, error, not judged), so that I can read every failed reply.
25. As an Editor, I want each listed Conversation to show how many of its replies failed their Live Verdict, so that I can find the worst Conversations.
26. As an Editor, I want to add a failed reply to the Evaluation Set with the existing "Add to Evaluation Set", so that a live failure becomes a regression case.
27. As an Owner, I want the Purge to clear a Live Verdict's reasons and keep its pass or fail, so that the Live score stays the same after the Retention Window and Visitor text doesn't outlive it.
28. As an Owner, I want Deleting a Conversation to clear its Live Verdicts' reasons at once, so that a deletion request removes everything quoting the Visitor.

### Live score

29. As an Editor, I want a Live score KPI card for each Version with its Wilson interval and sample size, so that I can see how well a Version answers.
30. As an Editor, I want the Live score marked Low sample under 30 Live Verdicts, so that a handful of judgements doesn't look decisive.
31. As an Editor, I want the Live score in the Version comparison with a higher score as the Better side, so that I can compare two Versions on quality as well as votes.
32. As an Editor, I want the Live score as a Time series metric with Live History markers, so that I can see quality change across releases.
33. As an Editor, I want only Visitor Conversations to count, so that the Live score matches the other Version KPIs.
34. As an Editor, I want the Live score to read the same before and after the Purge, so that history is stable.
35. As an Editor, I want the Live score's CSV export column in the Version comparison, so that it goes into reports with the other KPIs.

### Live score drop alert

36. As an Owner, I want an alert when a newly Live Version's Live score is clearly lower than the previous Live Version's, so that a bad Publish is caught without anyone watching the charts.
37. As an Owner, I want the alert to wait until the new Version has 30 Live Verdicts, so that it doesn't fire on noise.
38. As an Owner, I want moderate drops (around 10 points) to alert once there are enough Live Verdicts, so that the alert is useful and not just for disasters.
39. As an Owner, I want drops of less than 5 points never to alert, so that tiny significant dips stay quiet.
40. As an Owner, I want one email per alert with links to the Version comparison and to the Conversations viewer filtered to failed Live Verdicts, so that I can act straight away.
41. As an Editor, I want a "Live score drop" badge on the Agent list and the Agent page while the alert stands, so that everyone sees it.
42. As an Editor, I want the alert to clear when the drop is no longer clear or another Version is made Live, so that the badge reflects the present.

### Evaluation budget

43. As an Owner, I want to set a monthly Evaluation budget in US dollars in Organisation settings, so that judging live traffic can't spend more than I allow.
44. As an Owner, I want no budget by default and sampling impossible without one, so that turning on judging is a deliberate cost decision.
45. As an Owner, I want a meter of this month's spend against the budget in Organisation settings and on the Cost page, so that I can see how close it is.
46. As an Owner, I want sampling to pause across the Organisation once the month's spend reaches the budget, so that the limit holds.
47. As an Owner, I want one email when the budget is spent, so that I know judging has paused.
48. As an Owner, I want raising the budget to resume sampling at once, so that I can lift the pause.
49. As an Owner, I want the budget to reset on the 1st of each month (UTC), so that a spent budget doesn't stop judging for good.
50. As an Owner, I want Visitor replies never affected by the Evaluation budget, so that judging can never take an Agent offline.
51. As an Owner, I want Evaluation Runs that Editors start never capped by the budget, so that pre-Publish checks always work.
52. As an Owner, I want Evaluation budget changes recorded as Audit Events, so that spend decisions are accounted for.
53. As an Owner, I want Live Verdict Cost in Organisation cost's Evaluation column, so that I see what live judging spends next to Evaluation Runs.
54. As an Owner, I want Live Verdict Cost never counted in the Token Budget or Version KPIs' cost, so that judging never blocks Visitors or distorts cost per Conversation.

### Permissions, demo and accessibility

55. As an Editor, I want to set the Live sample rate, so that judging is part of my normal work.
56. As an Editor, I don't want to change the Evaluation budget, so that Organisation spend stays with Owners.
57. As a Member, I want to see Live Verdicts, the Live score and the alert badge, so that quality is visible to everyone who can see Conversations.
58. As a Member of another Organisation, I must never see another Organisation's Live Verdicts, Live score or budget.
59. As a prospective customer watching the demo, I want the HR helper's v2 to show a lower Live score than v1 in the Version comparison, so that I see live judging confirm the revert.
60. As a keyboard or screen-reader user, I want the new Trace section, filter, KPI card, badge and settings to be operable and announced, so that live evaluation is accessible.

## Implementation Decisions

- **Where it lives.** Live judging extends the existing `evaluation` module: it already owns judging, the Evaluation Model and the fake judge. The Live score extends `analytics` (rollups, KPIs, comparison, Time series, alerts). The sample rate extends the Operational Settings. Nothing new reaches into another module's tables.
- **Schema.**
  - **Live Verdict:** one row per sampled Agent Message (unique on the Message). Status (`pending`, `judged`, `error`, `skipped`), the two outcomes (`grounded`, `answers_question`, each `pass` or `fail`), their reasons, the overall pass, an error reason, the Evaluation Model used (copied), Cost and token usage, timestamps, and a purged-at stamp. It references the Message, the Agent and the Agent Version (copied from the Message's attribution).
  - **Operational Settings:** `live_sample_rate`, a whole percentage from 0 to 100, default 0.
  - **Organisation:** `evaluation_budget_usd` (nullable decimal; null means none), plus a monthly spend record per Organisation and calendar month (UTC): spend so far and whether the budget-spent email has been sent.
  - **Usage rollup:** two new counts per Agent Version and day, Live Verdicts judged and passed. Errors and skipped ones aren't counted.
  - **Agent:** a Live score drop alert flag beside the existing Budget alert and Block rate alert flags, plus the Version it was raised against.
- **Choosing a reply.** In the serving path, after a Visitor reply's `DoneEvent` is stored, a reply is a candidate when it wasn't a Guardrail block, wasn't the Fallback Text and its Agent's Live sample rate is above 0. It is chosen when a random draw falls under the rate and the Organisation's budget for the month isn't spent. A chosen reply gets a `pending` Live Verdict row and a Celery task, both after commit. The draw uses one module-level random source that tests can seed. It is not a new port.
- **Judging.**
  - The task loads the Message, its Remembered turns (the Version's setting, as the reply used them), the question, the Chunks it was given with their cited flags, and the reply. If the Message or any of those turns is Purged, the Live Verdict becomes `skipped`.
  - It calls spec 14's judge through the Model gateway with the Evaluation Model, extended with a new check, `answers_question`, and a new data block for earlier turns. Grounding stays as spec 14 defines it. Both checks come from one structured-output call at temperature 0. Earlier turns, the question, the reply and the Chunks are spotlighted data blocks with escaped delimiters, as the judge already does.
  - The system prompt and Project Instructions are never sent to the judge.
  - A judge error or timeout makes the Live Verdict `error` with the reason. There's no retry, so a provider outage doesn't multiply spend.
  - The judge's Cost is frozen with the existing cost function and Price table, stored on the row, added to the Organisation's monthly spend, and counted in Organisation cost's Evaluation column on the day of the judgement.
- **The budget.**
  - The spend check at sampling time reads the monthly record. Adding a judgement's Cost to it is an atomic update. The judgement that takes the spend to or past the budget sends the one email to Owners (guarded by the record's flag).
  - Judgements already pending when the budget is reached still finish. That can overshoot by at most the in-flight judgements, which is accepted and noted on the meter.
  - A new month is a new record, so the budget resets without a job. Raising the budget takes effect at the next sampling check.
  - Setting `live_sample_rate` above 0 is refused with a typed error while the Organisation has no budget. Removing the budget leaves existing rates as they are but stops all sampling.
- **Live score.**
  - The hourly rollup adds each day's judged and passed counts by the day of the reply, not of the judgement. A Live Verdict that arrives after its day is final doesn't move that day, as with Message Feedback.
  - The Version KPIs read the counts plus today's live partial day, and add the Live score with its Wilson interval (the existing function) and Low sample under 30 judged.
  - The Version comparison adds the row (higher is better, difference in percentage points) and its CSV column. The Time series adds the metric.
- **The alert.** It runs in the existing hourly alerts step after the rollup, beside the Block rate check:
  - For each Agent whose Live Version has at least 30 judged Live Verdicts since it became Live, the previous Live Version is the one before it in Live History. Its Live score is taken over its last 30 days as Live.
  - The check is a one-sided pooled two-proportion z-test at 95% (z > 1.645) **and** a drop of at least 5 percentage points.
  - Raising the alert sets the flag and the Version, and emails every Owner once. The email links to the Version comparison of the two Versions and to the Conversations viewer filtered to the Agent's failed Live Verdicts.
  - The flag clears when a later run no longer finds the drop, or when the Live Version changes (publish, revert or Bulk operation). A later drop alerts again.
  - An Agent with no previous Live Version, or whose previous Version has fewer than 30 judged Live Verdicts, is never alerted.
- **Retention.** The Purge clears a Live Verdict's reasons and stamps it purged-at in the same pass that purges its Message. Outcomes, Cost and counts stay. Deleting a Conversation goes through the same path. Live Verdicts are not an exception to retention, unlike ADR-0016's Evaluation Cases.
- **API.**
  - The Trace payload gains the Live Verdict (status, outcomes, reasons or "Text purged").
  - The Conversations viewer list gains the Live Verdict filter (`passed`, `failed`, `error`, `not_judged`) and a failed count per Conversation.
  - Operational Settings get and set `live_sample_rate` (audited as `agent.live_sample_rate_changed` with before and after).
  - Organisation settings get and set the Evaluation budget (Owners; audited as `organisation.evaluation_budget_changed`) and read this month's spend.
  - The Agent list and Agent read gain the alert flag. The Version KPIs, Version comparison and Time series responses gain the Live score.
  - Everything flows into the OpenAPI schema and the generated client.
- **Permissions.** Editors and Owners set the Live sample rate. Owners set the Evaluation budget. Every Member can read Live Verdicts, the Live score, the alert and the meter. An archived Agent's replies are never sampled, since it has no Visitors.
- **Studio UI (Tidepool throughout).**
  - **Embed & limits:** a Live sample rate field with "Judged by the Evaluation Model; costs count against the Evaluation budget". It is disabled with a link to Organisation settings when no budget is set.
  - **Trace:** a Live Verdict section (two outcomes with reasons, pending, error, skipped or not judged).
  - **Conversations viewer:** the Live Verdict filter and the failed count.
  - **Analytics:** the Live score KPI card, comparison row and Time series metric.
  - **Agent list and Agent page:** the "Live score drop" badge, on the existing badge mechanism.
  - **Organisation settings (Models):** the Evaluation budget field and this month's meter, beside the Evaluation Model and Evaluation repeats.
  - **Cost page:** the meter above the table. Live Verdict Cost goes in the existing Evaluation column.
- **Fakes and the demo.**
  - The fake judge and the Demo model's judging path gain the `answers_question` check by rule: it passes when the reply shares a scripted key phrase with the question.
  - The seed sets the Organisation an Evaluation budget and the HR helper a Live sample rate. It plays Live Verdicts for v1's and v2's seeded Visitor replies through the normal sampling path under the seed clock (ADR-0012), so v2's uncited replies fail grounding and its Live score is clearly lower in the Version comparison.
  - The alert would have been raised while v2 was Live and cleared by the revert to v1. The seed doesn't fake a standing alert on the current Live Version.
- **Glossary.** Live sample rate, Live Verdict, Live score and Evaluation budget in `GLOSSARY.md`, plus the Live score drop alert, which this spec adds to the glossary.

## Testing Decisions

- **Good tests** drive the feature through the HTTP API, as the Studio and widget do, and assert on responses and state read back through the API. They don't assert on judge prompt strings, apart from extending spec 14's contract test to show earlier turns are passed as spotlighted data and the system prompt is never sent.
- **No new seams.** Spec 15 uses the shared seams in [the specs README](./README.md#shared-test-seams). The judge is the existing **chat model** port, scripted with `FunctionModel`. Time is the **clock** fake and email the **mailer** outbox. The sampling draw is seeded through test settings, not faked behind a port.
- **API seam (primary):**
  - Sampling: 0% never samples and 100% always does. A Guardrail block, a Fallback Text reply and a Playground reply are never sampled. A seeded 50% run samples a stable subset. There's no sampling without a budget or once it's spent, and Visitor replies are unchanged either way.
  - Live Verdicts: both checks pass, either fails, and the reasons are kept. A judge error becomes Error and is left out. A Message Purged before judging is skipped. Earlier turns reach the judge. The Evaluation Model and Cost are recorded. Organisation isolation holds.
  - Budget: setting a rate without a budget is refused. Spend accumulates. One email arrives when the budget is reached, and in-flight judgements finish. Raising the budget resumes sampling. A new month resets it. Evaluation Runs aren't capped. The Audit Events are recorded.
  - Live score: KPIs with the Wilson interval and Low sample, the comparison row and Better side, the CSV column, the Time series, and the live partial day.
  - The Conversations viewer filter and failed counts. The Trace payload in every Live Verdict state.
- **Task seam:**
  - The judging task runs eagerly after a widget reply.
  - The hourly rollup adds judged and passed counts by the reply's day. A late Live Verdict doesn't move a finalised day.
  - The alert: not raised under 30 judged or with no previous Version; not raised for a significant drop under 5 points; raised for a clear drop with one email; cleared when the drop goes; cleared on publish and on revert; raised again on a later drop.
  - The Purge clears reasons and keeps outcomes, and the Live score is unchanged. Deleting a Conversation does the same at once.
- **Frontend network seam (MSW):** the Live sample rate field (disabled without a budget), the Trace section in each state, the Conversations viewer filter and count, the KPI card, comparison row and Time series metric, the badge, the budget field and meter for Owners (read-only for Editors), the Cost page meter, and accessibility of the new controls.
- **End-to-end seam:** on the seeded stack, set the HR helper's Live sample rate to 100%, send a widget message, see its Live Verdict in the Conversations viewer's Trace, filter to failed replies, and add one to the Evaluation Set. The axe checks cover the Trace section and Organisation settings.
- **Seed tests:** the existing seed tests extended to check the HR helper's Live Verdicts and that v2's Live score is lower than v1's.
- **Live suite:** one real-provider Live Verdict of a seeded reply, judged by a real model, run nightly outside the coverage gate.
- **Prior art:**
  - The Block rate alert and Budget alert tests (hourly check, badge, one email, clearing).
  - The Token Budget's daily counter tests (a spend counter that resets by period).
  - Spec 14's judge tests with a scripted `FunctionModel` and its prompt contract test.
  - The Version KPI, comparison and Time series tests for a new rate metric (thumbs-up rate).
  - The retention Purge tests.

## Out of Scope

- **Suggestions (spec 16):** reading failed Live Verdicts, thumbs-down replies and failed Evaluation Cases to propose changes to an Agent's Draft.
- Further judged checks: whether a reply should have been the Fallback Text, or wrongly was.
- Judging Playground replies, or judging a reply more than once.
- Sampling rules other than a flat random rate (by Tag, by question type, more replies with a thumbs-down).
- Automatic actions on the alert, such as reverting the Live Version.
- A budget per Agent or per Project, or one in any currency other than US dollars. A display currency for the whole Organisation would be its own spec.
- Capping Evaluation Runs that Editors start.
- Re-judging past replies when the Evaluation Model changes.

## Further Notes

- **Sampling never touches the reply.** The draw, the row and the task all happen after the reply is stored. A failure anywhere in judging leaves the Visitor's experience unchanged.
- **Why both checks in one call.** "Answers the question" needs the judge as much as grounding does. Asking for both in one structured call costs a few output tokens more than grounding alone, not a second call.
- **Why the test and the minimum drop.** Non-overlapping Wilson intervals would only alert on very large drops at 30 Live Verdicts (about 80% to 60%). The one-sided test alerts on drops of about 15 points at 30 Live Verdicts and about 9 points at 100. The 5-point floor keeps tiny but significant dips on busy Agents quiet. How fast a drop is found depends on the Live sample rate: at 5%, 100 Live Verdicts take about 2,000 Visitor replies. Checking every hour will occasionally raise a borderline false alarm, which is acceptable for an advisory badge.
- **Visitor text stays in the Retention Window.** A Live Verdict's reasons can quote the Visitor, so they are Purged with the Message. Don't copy Live Verdict reasons anywhere the Purge doesn't reach.
- **The budget is in US dollars** because every Cost in the product is (Price table, Price overrides, Organisation cost). A budget in another currency would need an exchange rate and would drift against the costs it caps.
- **Tickets:** to be written under `docs/tickets/15-live-evaluation/`.
