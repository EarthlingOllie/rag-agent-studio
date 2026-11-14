# Spec 14: Evaluation loop

**Status:** ready-for-agent · **Builds on:** [Spec 05](./05-versioning-project-instructions-spec.md), [Spec 07](./07-feedback-logging-comparison-spec.md), [Spec 08](./08-guardrails-evaluation-spec.md), [Spec 13](./13-agentic-retrieval-spec.md) · **Decision:** [ADR-0016](../adr/0016-evaluation-cases-outlive-retention.md)

## Problem Statement

The Studio shows Editors what happened, but not what will happen. Every Agent Message has a Trace, Visitors leave Message Feedback and Conversation Ratings, and Version comparison puts two Versions' KPIs side by side. All of that comes after the fact:

- **Publishing is a guess.** An Editor changes the Draft's Instructions, Top-k or Retrieval Mode, tries a few questions in the Playground, and Publishes. Nothing checks the change against the questions that went wrong before. The first sign of a bad Version is Visitors' thumbs going down over the following days, and only once there's enough of them to leave Low sample.
- **Failures are seen, then lost.** An Editor reads a thumbs-down in the Conversations viewer and knows exactly what the Agent should have said, but there's nowhere to keep that knowledge. After the Retention Window the Purge clears the Message text, and the lesson goes with it.
- **The same mistake comes back.** A fix for one question can quietly break another. Without a fixed set of questions answered by both the old and the new configuration, nobody can tell.
- **Project Instructions rollouts are blind.** One Instructions edit reaches every Agent through Bulk publish, built from each Agent's Live configuration. That is the change most likely to break something and the least tested.
- **The only evaluation is about safety.** The Attack evaluation suite proves the Guardrails work. Nothing measures whether answers are right, grounded in the Knowledge Base, or honest about what it doesn't cover.

## Solution

Each Agent gets an **Evaluation Set**: questions its Editors care about, each with what a good answer must do. An **Evaluation Run** answers every case with two sides at once, normally the Live Version and the Draft, against the same Knowledge Base. The Organisation's **Evaluation Model** judges each answer. Publishing then shows what the change would break.

- **Build the set from real failures.** "Add to Evaluation Set" on any Agent Message, in the Conversations viewer or the Playground, copies the Visitor's question into a new **Evaluation Case** and offers the passages the Agent cited as possible Expected sources. The Editor says what a good answer is:
  - an **Expected source** (a passage the answer should retrieve and cite);
  - a **Reference answer** (what it should say);
  - or **Expect Fallback Text** (it should say it doesn't know).

  Cases are kept until an Editor deletes them, past the Retention Window (ADR-0016).
- **Evaluate before Publishing.** From the new **Evaluation** Agent view, or straight from the Publish dialog, an Editor starts a Run after seeing its estimated Cost.
  - Each side answers every case as many times as the Organisation's **Evaluation repeats**, through the real Guardrails.
  - Each answer gets pass/fail **Verdicts** with the judge's reasons, and a case passes on a side when most of its repeats pass.
  - The Run shows each side's **Evaluation score** and every **Regression**: a case that passes on Live and fails on the Draft.
- **Warnings, never blocks.**
  - **Publish:** the Publish dialog warns about Regressions or a lower score, and shows a notice when the Draft hasn't been evaluated, its Run is stale, or the chosen Instructions differ from the ones it ran with.
  - **Bulk publish:** its rollout dialog offers a **Rollout evaluation**, which runs each Agent's Live configuration with the new Instructions against Live as it is.
- **Keep the set honest.** An Expected source whose Document is deleted, or whose passage disappears from a new Edition, becomes a **Stale expectation**: it is skipped, and its case is flagged. The Studio gives an **Expected source warning** before an Editor deletes or replaces such a Document.
- **Owners stay in control of cost.** Owners choose the Evaluation Model and the Evaluation repeats in Organisation settings. Each Run's Cost is frozen when it runs, shown on the Run, and counted in a new Evaluation column in Organisation cost. It never counts in Version KPIs or the Token Budget.
- **The demo tells the story.** The Demo Organisation's HR helper has an Evaluation Set and two finished Runs. The Run of v2 against v1 shows the Regressions behind the revert.

## User Stories

### Evaluation Set and cases

1. As an Editor, I want each Agent to have its own Evaluation Set, so that cases fit that Agent's Tag scoping, Instructions and Retrieval Mode.
2. As an Editor, I want to write an Evaluation Case by hand, so that I can test questions no Visitor has asked yet.
3. As an Editor, I want every case to need at least one expectation, so that every case checks something.
4. As an Editor, I want to set an Expected source by choosing a passage of a Document, so that a case checks the answer was grounded in the right material.
5. As an Editor, I want to write a Reference answer in my own words, so that the judge checks meaning, not wording.
6. As an Editor, I want to mark a case Expect Fallback Text, so that I catch an Agent making up answers the Knowledge Base doesn't hold.
7. As an Editor, I want a case to hold several Expected sources, so that a question whose answer spans two Documents can be checked properly.
8. As an Editor, I want to edit and delete cases, so that the set stays accurate as the Agent's purpose changes.
9. As an Editor, I want the set capped at 200 cases with a clear message at the limit, so that a Run stays bounded in time and Cost.
10. As an Editor, I want to copy cases from another Agent in the same Project, so that related Agents share a starting set.
11. As an Editor, I want copied cases to be independent copies, so that editing one Agent's case never changes another's.
12. As an Editor, I want cases flagged when they have a Stale expectation, so that I know which ones to fix.
13. As an Editor, I want to see each case's latest result (pass, fail, Unsteady, Error) in the set, so that I can spot weak cases at a glance.
14. As an Editor, I want to search and filter the set by expectation kind, flag and latest result, so that a large set stays manageable.

### Adding cases from real traffic

15. As an Editor, I want "Add to Evaluation Set" on any Agent Message in the Conversations viewer, so that a thumbs-down becomes a test in a few clicks.
16. As an Editor, I want the same action on Playground answers, so that something I find while testing a Draft is kept.
17. As an Editor, I want the Visitor's question copied in and editable before saving, so that I can remove personal details or rewrite a follow-up as a standalone question.
18. As an Editor, I want the passages the Agent cited offered as possible Expected sources, unticked, so that I can keep the right ones without assuming they were right.
19. As an Editor, I want the action to tell me the case keeps no link to the Conversation, so that I understand what is copied.
20. As an Owner, I want adding a case from a Message recorded as an Audit Event, so that every copy of Visitor text past the Retention Window is accounted for.
21. As an Owner, I want deleting a case recorded as an Audit Event, so that the set's history can be reconstructed.
22. As an Owner, I want cases kept after the Purge, so that the regression set doesn't empty itself every Retention Window.
23. As an Owner, I want the Visitor's Conversation still purged and deletable as before, so that the Retention Window still holds for Conversations.

### Running an evaluation

24. As an Editor, I want an Evaluate action on the Evaluation view and in the Publish dialog, so that I can check a Draft where I decide to Publish.
25. As an Editor, I want a Run to compare the Live Version with the Draft by default, so that it answers the question Publish asks.
26. As an Editor, I want to choose any two sides, each the Draft or a Version, so that I can ask which of v3 and v5 does better on today's Knowledge Base.
27. As an Editor, I want the Draft side to answer with the Instructions I choose (the Current Instructions Version by default, or the Instructions Draft), so that I test exactly what I mean to publish.
28. As an Editor, I want a Version side to answer with the Instructions it pins, so that a Version is measured as it actually runs.
29. As an Editor, I want both sides answered at the same moment against the same Knowledge Base, so that a Document change between runs can't masquerade as an Agent change.
30. As an Editor, I want answers to go through the real Guardrails and each side's own Retrieval Mode, so that the Run reflects what Visitors would get.
31. As an Editor, I want to see the estimated Cost before starting, so that I don't spend more than I meant to.
32. As an Editor, I want to see a Run's progress while it runs, so that I know it hasn't stalled.
33. As an Editor, I want to cancel a running Run, so that a mistake doesn't keep spending.
34. As an Editor, I want Evaluate disabled while a Run is in progress for that Agent, so that two Runs don't compete.
35. As an Editor, I want a Run on an Agent that has never been Published to answer with the Draft alone, so that I can build a baseline before going live.
36. As an Editor, I want a Run with a Draft side marked stale once the Draft has a newer Draft revision, so that I never trust results for a configuration that has since changed.
37. As an Editor, I want a Version whose Provider Credential is gone refused as a side, with the reason, so that a Run doesn't fail halfway.

### Results

38. As an Editor, I want each side's Evaluation score, so that I see the overall direction.
39. As an Editor, I want the Regressions listed first, so that I see what the change breaks.
40. As an Editor, I want cases that fail on Live and pass on the Draft shown as improvements, so that I see what the change fixes.
41. As an Editor, I want each case's Verdicts per expectation with the judge's one-sentence reason, so that I can tell whether to fix the Agent or the case.
42. As an Editor, I want a grounding Verdict on every answered case, so that I catch answers whose claims aren't supported by their Citations.
43. As an Editor, I want each answer with its Trace (Searches, Message retrievals, Citations, Guardrail outcomes), so that I can see why it failed.
44. As an Editor, I want each case's repeat count shown (for example 2/3) and Unsteady cases marked, so that I know which results are borderline.
45. As an Editor, I want a case that couldn't be answered or judged marked Error with the reason, and left out of the score, so that a provider outage doesn't look like a regression.
46. As an Editor, I want a Guardrail block on a harmless case judged as a fail, so that over-eager Guardrails show up as a regression.
47. As an Editor, I want Stale expectations shown as skipped, neither pass nor fail, so that Knowledge Base changes don't get blamed on the Agent.
48. As an Editor, I want every finished Run kept as the Agent's history, with its sides, Instructions, Evaluation Model, repeats and Cost, so that I can see a case flip over time and know what produced each result.
49. As an Editor, I want a Run's Cost split into answers and judging, so that I know what drives it.

### Publishing

50. As an Editor, I want the Publish dialog to warn when the Draft's latest Run against the current Live Version has Regressions or a lower Evaluation score, listing the Regressions with their reasons, so that I publish knowing what breaks.
51. As an Editor, I want to Publish anyway after that warning, so that a noisy judge or a deliberate trade-off never stops me.
52. As an Editor, I want a notice when the Draft has no Run, its Run is stale, or the Live Version changed since the Run, so that I know the evidence is missing or out of date.
53. As an Editor, I want a notice when I'm publishing with different Instructions than the Run used ("evaluated with Instructions v3, publishing with v2"), so that I know the Run doesn't describe this Publish.
54. As an Editor, I want a one-line hint in the Publish dialog when the Agent has no Evaluation Set, so that I discover the feature where it matters.
55. As an Editor, I want the rollout dialog to offer Rollout evaluation for the selected Agents, so that I can see what new Project Instructions do to each Agent before rolling them out.
56. As an Editor, I want the rollout dialog to list each Agent's Regressions and mark Agents without an Evaluation Set "not evaluated", so that I know where the rollout is untested.
57. As an Editor, I want Rollout evaluation never to block the rollout, so that it informs the decision and doesn't take it.

### Keeping cases valid

58. As an Editor, I want a warning before deleting a Document that holds an Expected source, naming the Agents and the number of cases, so that I don't break cases unknowingly.
59. As an Editor, I want the same warning before uploading a new Edition of such a Document, so that I know cases may go stale.
60. As an Editor, I want Expected sources checked again as soon as a new Edition is Ready, so that broken cases are flagged straight away, not at the next Run.
61. As an Editor, I want Expected sources whose passage survives a new Edition to keep working, so that routine Document updates don't break my set.

### Organisation settings and cost

62. As an Owner, I want to choose the Evaluation Model in Organisation settings (Models), so that every Run in the Organisation is judged the same way.
63. As an Owner, I want the Default Model used when no Evaluation Model is chosen, so that evaluation works with no setup.
64. As an Owner, I want changing the Evaluation Model recorded as an Audit Event, so that a jump in scores can be traced to it.
65. As an Owner, I want the Evaluation Model's credential protected from deletion while it is chosen, so that Runs don't break.
66. As an Owner, I want to set Evaluation repeats to 1, 3, 5, 7 or 9 (3 by default), so that I trade confidence against Cost.
67. As an Owner, I want changing Evaluation repeats recorded as an Audit Event, so that changes to Run Cost can be explained.
68. As an Owner, I want Run Cost in its own Evaluation column in Organisation cost, so that I see what evaluation spends.
69. As an Owner, I want Runs left out of Version KPIs and the Token Budget, so that testing never distorts Visitor metrics or blocks Visitors.

### Permissions and lifecycle

70. As an Editor, I want to manage Evaluation Sets and start Runs, so that evaluation is part of my normal work.
71. As an Editor, I don't want to change the Evaluation Model or Evaluation repeats, so that Organisation-wide cost settings stay with Owners.
72. As a Member, I want an archived Agent's Evaluation Set and Runs kept but no new Run allowed, so that restoring it brings its set back.
73. As an Owner, I want Permanent deletion of an Agent to take its Evaluation Set and Runs with it, so that nothing is left over.
74. As a Member of another Organisation, I must never see or reach another Organisation's Evaluation Sets or Runs.

### Demo and accessibility

75. As a prospective customer watching the demo, I want the HR helper to show an Evaluation Set with cases added from thumbs-down Messages and a Run of v2 against v1 with Regressions, so that I see feedback turn into a caught regression.
76. As a keyboard or screen-reader user, I want the Evaluation view, the case editor, Run detail and the new dialog sections to be fully operable and announced, so that evaluation is accessible.

## Implementation Decisions

- **New backend module: `evaluation`.** It owns Evaluation Sets, cases, Runs, judging, the cost estimate and the warning summaries. Other modules call into it through a small interface; it calls the runtime, retrieval, the Model gateway and pricing modules and doesn't reach into their tables.
- **Schema.**
  - **Evaluation Case:** Agent, question (text up to the Visitor message limit), Reference answer (optional), Expect Fallback Text (boolean), source (`written` or `from_message`), created_by, timestamps. Validation: at least one expectation. Expect Fallback Text can't be combined with an Expected source or a Reference answer, because they contradict it. At most 200 cases per Agent, enforced under a lock on the Agent.
  - **Expected source:** case, Document, passage text (up to 1,000 characters), Stale flag and the reason it is stale (`document_deleted`, `passage_missing`). It references the Document, not a Chunk, because Chunks are replaced with every Edition. Deleting the Document leaves the row and marks it stale; the Document's name is kept as a tombstone for display.
  - **Evaluation Run:** Agent, status (`queued`, `running`, `completed`, `failed`, `cancelled`), kind (`agent` or `rollout`), started_by, the Evaluation Model and Evaluation repeats in force when it started (copied, so later setting changes don't rewrite history), progress (answers done out of total), estimated and actual Cost (answers and judging separately, frozen with the existing cost function and price table), error message, timestamps.
  - **Run side** (two per Run, `first` and `second`; one when the Draft runs alone): kind (`draft` or `version`), the Agent Version (for `version`), the Draft revision it ran (for `draft`), and the Instructions it answered with (an Instructions Version, or the Instructions Draft marker), plus a snapshot of the effective AgentConfig and Instructions text actually run.
  - **Case result:** Run, side, case, repeat number, the answer text, its Trace payload (Searches, retrievals with scores and cited flags, Citations, Guardrail outcomes, tokens, latency), Cost, and status (`answered`, `error`) with an error reason. A copy of the question is stored with the Run, so editing or deleting a case later doesn't rewrite a past Run.
  - **Verdict:** case result, kind (`expected_source`, `reference_answer`, `fallback`, `grounding`), outcome (`pass`, `fail`, `stale`), and the judge's reason for judged kinds.
  - **Organisation settings:** an **Evaluation Model** row per Organisation, copying the Default Model's shape (a Provider Credential reference registered so the credential can't be deleted, plus the model name), and `evaluation_repeats` on the Organisation (one of 1, 3, 5, 7 or 9; default 3).
  - Evaluation Cases, Runs and their results are never touched by the Purge (ADR-0016). They hold no reference to any Conversation or Message.
- **Resolving a side to something runnable.**
  - A Draft side uses the Draft's AgentConfig and the chosen Instructions. A Version side uses the Version's AgentConfig and its pinned Instructions Version.
  - A rollout side uses the Live Version's AgentConfig with the new Instructions Version. It is created only by Rollout evaluation, never through the general Run API.
  - The chat model, reranker and LLM classifier are resolved from the side's AgentConfig exactly as for a Visitor reply, falling back to the Default Model. A side whose Provider Credential is gone is refused at start with a typed error, as Revert already does.
  - This lookup currently lives as private helpers in the Playground and serving modules. Prefactor it into one public "resolve an AgentConfig to models" function that Playground, serving and evaluation all use, rather than copying it.
- **Answering.**
  - Each answer calls the Guardrail pipeline's `run_turn` with no history, the side's AgentConfig and Instructions, the resolved models, and the real retrieval function scoped to the Agent's Project.
  - Answering **creates no Conversation and no Message**, so Version KPIs, Usage rollups, the Token Budget, Admission control and Rate limits never see a Run.
  - The answer, Trace payload and Cost are written to the case result from the `DoneEvent`.
  - Provider errors and timeouts make the case result `error`. A Guardrail block is a normal answer and is judged.
- **Judging.**
  - The Evaluation Model is called once per answer through the Model gateway. It is a structured-output call (Pydantic AI) at temperature 0, with its own timeout.
  - Input: the question, the answer, the text of the Chunks the answer cited (spotlighted as data, like retrieved Chunks), and the Reference answer if there is one.
  - Output: a pass/fail with a one-sentence reason for `reference_answer` (if present) and for `grounding` (every factual claim supported by a cited Chunk; an answer that is the Fallback Text skips grounding).
  - Judge usage is costed with the existing cost function and recorded as the Run's judging Cost. A judge error or timeout makes that case result `error`.
  - The judge prompt treats the answer and Chunks as data to assess, never as instructions, so a prompt-injected answer can't vote for itself.
- **Checks that need no model.**
  - `expected_source`: the passage is matched, after normalising case and whitespace, against the text of the Document's current-Edition Chunks. The Verdict is `stale` if the Document is gone or no Chunk contains the passage. Otherwise it is `pass` if any matching Chunk was cited in the answer, and `fail` if not (retrieved but uncited is a fail, recorded in the reason).
  - `fallback`: `pass` when the answer's `fallback` flag is set or its text equals the Agent's Fallback Text or Refusal text, otherwise `fail`.
- **Combining results.** A repeat passes when every Verdict that isn't `stale` passes. A case passes on a side when most of its answered repeats pass. A case is **Unsteady** when the repeats disagree on either side. It is an **Error** on a side when every repeat there errored, and Error cases are left out of that side's Evaluation score. A **Regression** passes on the first side and fails on the second. An **improvement** is the reverse.
- **The Run job.**
  - A Celery task enqueued by the start endpoint, following the Re-embed pattern: one row whose status and progress the Studio polls.
  - At most one queued or running Run per Agent, enforced with a partial unique index plus a lock at start (a second start is refused with a typed conflict).
  - Answers and judgements run with bounded concurrency so a Run doesn't monopolise a provider.
  - Cancelling sets the status to `cancelled`. The task checks it between answers and stops, and Cost spent so far is kept.
  - A Run where every case errored ends `failed`, with the most common error as its message.
  - The Run copies the question and expectations of every case at start, so editing the set mid-run doesn't change it.
- **Cost estimate.** cases × sides × repeats × each side's mean Cost per reply over the last 30 days (from the Usage rollups for Versions, from Playground Messages for the Draft), plus an estimate for judging from the Evaluation Model's prices and a fixed per-judgement token allowance. With no history, the side's model prices are used with the same allowance. The Evaluate dialog shows it as an estimate. It is stored on the Run for comparison with the actual Cost.
- **API (all under the Agent, Organisation-scoped like the rest).**
  - Cases:
    - list (with filters, latest result and Stale flags), create, read, update and delete;
    - copy from another Agent in the same Project;
    - a "prefill from Message" read, which returns the question before an Agent Message and its cited passages. It works for Visitor and Playground Messages of this Agent, and is refused if the text has been purged.
    - Creating with `source = from_message` records the Audit Event.
  - Runs:
    - estimate (given sides and Instructions), start, cancel;
    - list (the history), read (summary with scores, Regressions, improvements and progress);
    - read results (per case, with Verdicts and Trace payloads, paginated).
  - **Evaluation summary for Publish:** a read taking the Instructions Version the Publish dialog has chosen. It returns one state, `no_set`, `no_run`, `stale`, `instructions_differ`, `live_changed`, `regressions` or `clear`, with the latest qualifying Run's scores and Regressions. The Publish endpoint itself is unchanged. Warnings are advisory and read by the dialog.
  - **Rollout evaluation:** start, taking the new Instructions Version and the selected Agents; it starts one Run per Agent with an Evaluation Set and skips the others. A read returns per-Agent state for the rollout dialog.
  - **Expected source dependents:** a read on a Document returning the Agents and case counts holding an Expected source in it, used by the delete and new-Edition flows.
  - **Organisation settings:** get and set the Evaluation Model (Owners), and get and set Evaluation repeats (Owners). Organisation cost gains an `evaluation` amount per line.
  - Everything flows into the OpenAPI schema and the generated client as other routes do.
- **Expected sources after Ingestion.** When a Staged edition is swapped in, the evaluation module re-matches every Expected source on that Document and sets or clears Stale flags in the same transaction's after-commit hook. Deleting a Document marks its Expected sources stale with the `document_deleted` reason.
- **Audit Events.**
  - `agent.evaluation_case_added_from_message` holds the case id and Agent, not the question text.
  - `agent.evaluation_case_deleted`.
  - `organisation.evaluation_model_changed` and `organisation.evaluation_repeats_changed`, both with before and after values.
  - Writing and editing cases, and Runs, are not audited.
- **Permissions.**
  - Editors and Owners manage cases and start or cancel Runs, including Rollout evaluation.
  - Only Owners set the Evaluation Model and Evaluation repeats.
  - An archived Agent's set and Runs are readable and read-only, and starting a Run is refused.
  - Permanent deletion cascades to the set and Runs.
- **Studio UI (Tidepool design system throughout).**
  - **Evaluation Agent view,** the fifth tab between Versions and Embed & limits:
    - the Evaluation Set as an editable list with filters, Stale flags and latest results;
    - a case editor, with an Expected source picker that opens a Document's Chunks to select a passage;
    - copy from another Agent;
    - the Runs list (history, status, scores, Cost);
    - Run detail: the summary, Regressions first, then improvements, then the rest. Each case shows both sides' answers per repeat, its Verdicts with reasons and the Trace drawer.
  - **Evaluate dialog:** pick the sides (defaulting to Live against Draft) and the Draft's Instructions, see the estimate, start.
  - **"Add to Evaluation Set"** in each Agent Message's ⋯ menu in the Conversations viewer and the Playground. It opens the case editor with the question and unticked cited passages, and a line saying no link to the Conversation is kept.
  - **Publish dialog:** an Evaluation section above the note. It shows the warning with Regressions and their reasons, or a notice, or the no-set hint, plus an Evaluate action. The Publish button stays enabled in every state.
  - **Rollout dialog:** an Evaluate rollout action and a per-Agent column with Regressions, "not evaluated", running or clear.
  - **Documents:** the Expected source warning in the delete confirmation and before a new-Edition upload. The Document viewer marks passages used as Expected sources.
  - **Organisation settings (Models):** the Evaluation Model picker (with "Use the Default Model") and the Evaluation repeats segmented control, both for Owners only.
  - **Cost page:** an Evaluation column.
- **Fakes and the demo.**
  - The default fake chat model and the Demo model gain a deterministic judging path. Given the structured judge request, they pass a Reference answer when the answer contains a scripted key phrase, and pass grounding when the answer cites at least one Chunk. This keeps `docker compose`, end-to-end tests and the seed deterministic and free.
  - The seed adds the HR helper's Evaluation Set: about 12 cases, some added from seeded thumbs-down Messages through the API, and at least one Expect Fallback Text case. It also adds two finished Runs: v2 against v1 with Regressions, and the Draft against v3. Like the rest of the Seeded history, it is played through the API under the seed clock (ADR-0012).
- **Glossary.** The Evaluation section of `GLOSSARY.md` and the updated Agent view, Bulk publish, Organisation cost and Seeded history entries are the vocabulary for this spec.

## Testing Decisions

- **Good tests** drive the feature through the HTTP API, as the Studio does, and assert on responses and on state read back through the API. They don't assert on judge prompt strings, apart from one contract test showing the answer and Chunks are passed as spotlighted data.
- **No new seams.** Spec 14 uses the shared seams in [the specs README](./README.md#shared-test-seams). The judge is the existing **chat model** port.
- **API seam (primary):** real Postgres and Redis, with scripted Pydantic AI `FunctionModel`s for the Agent's answers and for the judge. It covers:
  - Case management: validation of expectations (including Expect Fallback Text exclusivity), the 200-case cap under concurrent creates, copying from another Agent, the Audit Events (added from Message, deleted), and isolation between Organisations and Projects.
  - Prefill from Message: Visitor and Playground Messages, cited passages offered, refusal for purged text and for another Agent's Message.
  - Runs: the estimate; start, conflict on a second start, cancel; a Draft-only Run for a never-published Agent; refusal of a side whose credential is gone and of an archived Agent.
  - Answering: the real retrieval used, each side's own Retrieval Mode and Instructions, no Conversation or Message created, Version KPIs and Token Budget unchanged.
  - Verdicts: expected source cited (pass), retrieved but uncited (fail), passage missing (stale); fallback pass and fail; a judged Reference answer and grounding with reasons; a Guardrail block judged as a fail; provider and judge errors as Error and left out of the score.
  - Combining: majority across repeats, Unsteady, Regressions and improvements, Evaluation score per side, and the repeats and Evaluation Model copied onto the Run.
  - Cost: answers and judging recorded separately and frozen at the prices in force when the Run happened (clock fake plus a price change); the Evaluation amount in Organisation cost.
  - The Evaluation summary for Publish, in every state: no set, no run, stale after a Draft revision, live changed, Instructions differ, Regressions, clear. Publishing still succeeds in every state.
  - Rollout evaluation: one Run per Agent with a set, Agents without one marked "not evaluated", and the rollout side answering with the new Instructions.
  - Organisation settings: Owner-only changes, the Default Model fallback, the credential reference blocking deletion, the audited changes.
- **Task seam:**
  - The Run job runs eagerly when started through the API: progress, cancel between answers, and `failed` when every case errors.
  - Ingestion of a new Edition re-matches Expected sources: a surviving passage stays valid and a missing one becomes stale.
  - Deleting a Document marks its Expected sources stale.
  - The Purge, called directly, clears the source Conversation and leaves the case untouched.
- **Frontend network seam (MSW):**
  - The Evaluation view: the set list with filters and flags, the case editor's validation and Expected source picker, copy from another Agent, the Runs list with polling while running, and Run detail ordering with Verdict reasons and the Trace drawer.
  - "Add to Evaluation Set" from the Conversations viewer and the Playground, prefilled and editable, with sources unticked.
  - The Evaluate dialog: side and Instructions pickers and the estimate.
  - The Publish dialog's Evaluation section in every summary state, with Publish always enabled.
  - The rollout dialog's per-Agent evaluation column.
  - The Expected source warning on delete and new-Edition upload.
  - Organisation settings: the Evaluation Model and repeats for Owners, read-only or hidden for Editors.
  - The Cost page's Evaluation column.
  - Accessibility of the new controls.
- **End-to-end seam:** on the seeded stack, open a seeded thumbs-down in the Conversations viewer, add it to the HR helper's Evaluation Set with a Reference answer, change the Draft, Evaluate, and see the Regression in the Publish dialog. The axe checks cover the Evaluation view and the Publish dialog.
- **Seed tests:** the existing seed tests extended to check the HR helper's Evaluation Set, the two finished Runs and the Regressions in the v2-against-v1 Run.
- **Live suite:** one real-provider Run of three cases (one per expectation kind) against the seed Knowledge Base, judged by a real model, run nightly outside the coverage gate.
- **Prior art:**
  - Re-embed's job, status and polling tests (a long job that shows progress).
  - Spec 07's Version comparison and Organisation cost tests.
  - Spec 08's Attack evaluation suite runner tests and the prompt-assembly contract test.
  - Spec 13's Playground tests with a scripted `FunctionModel`.
  - The Default Model tests (a Credential reference setting).
  - The retention Purge tests.

## Out of Scope

- **Scoring live traffic (spec 15):** sampling Visitor replies for the Evaluation Model to judge, an alert when a newly Published Version's judged quality drops, and an Evaluation budget that caps spend nobody starts by hand.
- Hard blocking of Publish or Bulk publish on evaluation results.
- Cases with several turns, or with Conversation history.
- Running a Run automatically on Draft save, on a schedule, or in CI against customers' Agents.
- Scores on a scale (1–5), weighted cases, or statistical significance between sides beyond majority across repeats.
- An Evaluation Model chosen per Agent or per Run.
- Comparing more than two sides in one Run, or across Agents.
- Importing or exporting Evaluation Sets (CSV or JSON), and sharing sets across Projects.
- Generating cases automatically from the Knowledge Base.
- Changing the Attack evaluation suite, which stays a separate safety check.

## Further Notes

- **Warn, never block.** Sets are small and judges are noisy. A hard gate would teach Editors to delete inconvenient cases. The Publish button stays enabled in every evaluation state, which matches the product's other warnings (Contrast Warning, Confounder note).
- **Both sides answer together for a reason.** The Knowledge Base is live and unversioned (ADR-0003). Comparing a Draft run today with a Live run last week would mix the two changes, so every Run answers both sides at the same moment, even though that doubles its Cost.
- **Repeats are fresh answers, not re-judgements.** Most of the noise comes from the Agent's own answer (sampling, and Agentic Search choices), so each repeat answers again and is judged once.
- **ADR-0016 is the one retention exception.** Cases and Runs never reference Conversations, and the question is copied with the Editor seeing and editing it. Don't add a link back "for convenience".
- **The judge is a chat model behind the Model gateway.** That keeps fakes in one place and lets the seed and end-to-end runs be deterministic. Keep the fake judge strict enough that it can fail: a judge that always passes would make the suite meaningless, the same lesson as the Naive model.
- **Prefactor first.** The model-resolution helpers are private to the Playground and serving modules today. Making them one public function is the first ticket, so evaluation doesn't copy them.
- **Tickets:** [`docs/tickets/14-evaluation-loop/`](../tickets/README.md#14-evaluation-loop): eleven tickets, 14-01 to 14-11.
  - 14-01 is a prefactor and 14-02 the tracer.
  - 14-03 to 14-05 follow the tracer; 14-06 and 14-07 follow 14-05.
  - 14-08 and 14-09 follow 14-03 and 14-04, and 14-10 follows 14-09.
  - 14-11 closes with the demo seed, the end-to-end test and the live suite.
