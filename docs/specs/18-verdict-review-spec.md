# Spec 18: Verdict review

**Status:** ready-for-agent · **Builds on:** [Spec 14](./14-evaluation-loop-spec.md), [Spec 15](./15-live-evaluation-spec.md), [Spec 16](./16-suggestions-spec.md) · **Decisions:** [ADR-0016](../adr/0016-evaluation-cases-outlive-retention.md), [ADR-0018](../adr/0018-reviews-measure-guidance-changes.md)

## Problem Statement

After specs 14 and 15 the Evaluation Model decides a great deal: whether a Draft has Regressions, every Version's Live score, the Live score drop alert, and much of the evidence Suggestions work from. Nobody knows how often it is right:

- **No measure of the Evaluation Model.** An Editor reads a Verdict's reason and sometimes thinks "that's wrong", but the thought goes nowhere. There is no number for how far Verdicts can be trusted, so a noisy Evaluation Model and a broken Agent look the same.
- **Thumbs can't be the yardstick.** Message Feedback is rare and, as spec 15 says, measures mood rather than quality. Comparing Live Verdicts with thumbs would mostly measure Visitors.
- **Doubted Verdicts aren't a fair sample.** If agreement were counted from whatever Editors happen to review, they would mostly review failures and odd reasons, and the number would say how often the Evaluation Model is right on the Verdicts people already doubted.
- **Changing the Evaluation Model is a guess.** An Owner can pick another Evaluation Model in Organisation settings but has nothing to compare the old and the new on.
- **Disagreements are lost.** The reasons an Editor disagrees are exactly what spec 19 needs to improve judging, and today they aren't written down.

## Solution

Editors give **Verdict reviews**: their own pass or fail on a judged Verdict or a Live Verdict check. The Studio counts **Evaluation Model agreement** from reviews made blind on a random **Review sample**.

- **What can be reviewed.** Judged Verdicts in Evaluation Runs (Reference answer and grounding) and both checks of a Live Verdict (grounded, answers the question). Expected source and Expect Fallback Text Verdicts aren't judged by the Evaluation Model, so there's nothing to review.
- **The Review sample.** An Organisation-level page serves one judged Verdict or Live Verdict check at a time, drawn at random from those by the current Evaluation Model that aren't yet reviewed and whose text still exists. The Editor sees the question, the answer, the Chunks it was given (with which were cited) and what is being checked, and says pass or fail *before* seeing the Evaluation Model's. Then the Evaluation Model's pass or fail and reason are revealed.
- **Reviews elsewhere.** On a Verdict in Run detail and a Live Verdict in the Trace, an Editor can agree or disagree with the shown pass or fail. Those reviews are kept and shown on the Verdict, but don't count towards agreement.
- **A reason when it differs.** When an Editor's review differs from the Evaluation Model's, they may say why (up to 1,000 characters).
- **One per Verdict, never an override.** A Verdict has at most one review, from any Editor, and reviewing it again replaces it. A review never changes the Verdict, the Evaluation score, Regressions, the Live score, alerts or Suggestions evidence.
- **Agreement.** Organisation settings › Models shows Evaluation Model agreement for the current Evaluation Model: the agreement rate with its Wilson interval (Low sample under 30), **false passes** (it passed, the Editor said fail) and **false fails**, overall and for each check. Earlier Evaluation Models keep their own figures.
- **The demo tells the story.** The seeded Organisation has about 40 Review sample reviews with a few false passes, so the agreement card reads like a real one.

## User Stories

### The Review sample

1. As an Editor, I want a Review sample page that gives me one judged Verdict or Live Verdict check at a time, so that reviewing is quick.
2. As an Editor, I want items drawn at random from every Agent in the Organisation, so that agreement isn't skewed towards the Verdicts I doubted.
3. As an Editor, I want only Verdicts by the current Evaluation Model in the sample, so that my reviews measure the Evaluation Model in use.
4. As an Editor, I want only items not yet reviewed, so that I don't review the same Verdict twice.
5. As an Editor, I want to see the question, the answer, the Chunks it was given with which were cited, and what is being checked, so that I can judge it myself.
6. As an Editor, I want to see a Live Verdict's Remembered turns, so that I judge a follow-up question in context, as the Evaluation Model did.
7. As an Editor, I want to see the Reference answer when the check is a Reference answer, so that I judge against the same expectation.
8. As an Editor, I want the Evaluation Model's pass or fail and reason hidden until I've given mine, so that I'm not swayed by it.
9. As an Editor, I want the Evaluation Model's pass or fail and reason shown straight after I review, so that I learn where it differs from me.
10. As an Editor, I want to add a reason when I differ from the Evaluation Model, so that the disagreement can be acted on later.
11. As an Editor, I want to skip an item I can't decide, so that I don't guess.
12. As an Editor, I want to see how many items I and the Organisation have reviewed, so that I know when agreement is no longer a Low sample.
13. As an Editor, I want a clear message when there is nothing to review, so that an empty sample doesn't look broken.
14. As an Editor, I want Live Verdicts whose reply was Purged left out of the sample, so that I'm never asked to judge text that no longer exists.
15. As an Editor, I want Live Verdicts with an Error, skipped Live Verdicts and Stale or Error Verdicts left out, so that only real judgements are reviewed.

### Reviewing where Verdicts are shown

16. As an Editor, I want to agree or disagree with a judged Verdict in Run detail, so that I can record a doubt where I read it.
17. As an Editor, I want to agree or disagree with each check of a Live Verdict in the Trace, so that I can do the same for live replies.
18. As an Editor, I want an existing review shown on its Verdict with who gave it, when, and whether it came from the Review sample, so that the team sees it.
19. As an Editor, I want to replace or remove a review, so that a mistake can be corrected.
20. As an Editor, I want reviews made outside the Review sample kept but not counted towards agreement, so that the measure stays unbiased.
21. As an Editor, I want a review I give in Run detail or the Trace to take that Verdict out of the Review sample, so that it isn't served again.

### Evaluation Model agreement

22. As an Owner, I want Evaluation Model agreement next to the Evaluation Model choice in Organisation settings › Models, so that I can judge the Evaluation Model where I choose it.
23. As an Owner, I want the agreement rate with its Wilson interval, so that I see how sure the number is.
24. As an Owner, I want agreement marked Low sample under 30 reviews, so that a handful of reviews doesn't look decisive.
25. As an Owner, I want false passes and false fails counted separately, so that I know whether the Live score is overstated or understated.
26. As an Owner, I want agreement for each check (grounding, answers the question, Reference answer), so that I see which kind of judgement is weak.
27. As an Owner, I want agreement kept for each Evaluation Model, with earlier ones listed, so that I can compare Evaluation Models after changing it.
28. As an Owner, I want a link from the agreement card to the Review sample, so that more reviews are one click away.
29. As an Owner, I want reviews never to change a Verdict or anything counted from Verdicts, so that the Evaluation score, Regressions, Live score and alerts mean what they meant.
30. As an Editor, I want a failed Live Verdict that I said was wrong still to count as Suggestions evidence, so that reviews stay a measure and never quietly change behaviour.

### Retention and privacy

31. As an Owner, I want the Purge to clear the reason on a Live Verdict's review together with its Message, so that an Editor's words quoting the Visitor don't outlive the Retention Window.
32. As an Owner, I want a Live Verdict's review to keep its pass or fail and keep counting after the Purge, so that agreement doesn't shrink as replies age.
33. As an Owner, I want Deleting a Conversation to clear its reviews' reasons at once, so that a deletion request removes everything quoting the Visitor.
34. As an Owner, I want reviews on Evaluation Run Verdicts kept with their Run, so that they last as long as the Run's answers.

### Permissions, demo and accessibility

35. As an Editor or Owner, I want to give Verdict reviews, so that reviewing is part of normal work.
36. As a Member, I want to see reviews and Evaluation Model agreement, so that trust in the Evaluation Model is visible to everyone.
37. As a Member of another Organisation, I must never see another Organisation's reviews, Review sample or agreement.
38. As a prospective customer watching the demo, I want the seeded Organisation's agreement card to show real-looking agreement with a few false passes, so that I see the Studio measure its own judge.
39. As a keyboard or screen-reader user, I want the Review sample, the review controls and the agreement card to be operable and announced, so that reviewing is accessible.

## Implementation Decisions

- **Where it lives.** Verdict reviews, the Review sample and agreement extend the `evaluation` module, which owns Verdicts, Live Verdicts and the Evaluation Model. The Purge extends `retention` through the path it already uses for Live Verdicts. Nothing new reaches into another module's tables.
- **Schema.**
  - **Verdict review:** one row per reviewed target. The target is either an Evaluation Verdict, or a Live Verdict plus its check (`grounded`, `answers_question`); unique per target. It holds the Editor's outcome (`pass` or `fail`), the Evaluation Model's outcome as it was (copied, so agreement never needs a join to change), the check kind (`grounding`, `answers_question`, `reference_answer`), the Evaluation Model it judged with (copied), `from_sample`, an optional reason (up to 1,000 characters), reviewed_by, reviewed_at, the Agent and the Organisation, and a purged-at stamp.
  - No new columns on Verdicts or Live Verdicts.
- **The Review sample.**
  - The pool is every judged Evaluation Verdict of kind Reference answer or grounding (outcome pass or fail), and both checks of every judged Live Verdict that isn't purged, by the Organisation's current Evaluation Model and with no review.
  - `next` picks one uniformly at random from the pool and returns what the Evaluation Model saw, without its outcome or reason: for a Run Verdict, the case's question, the Reference answer for that check, the answer and its Trace Chunks with cited flags; for a Live Verdict, its Remembered turns, the question, the reply and the Chunks it was given with cited flags.
  - Submitting stores the review with `from_sample` true and returns the Evaluation Model's outcome and reason for the reveal. If someone else reviewed the item in the meantime, the later review replaces it, as everywhere.
  - Skipping stores nothing; the item stays in the pool.
- **Reviews elsewhere.** Put and delete on a Verdict's review from Run detail and from the Trace store `from_sample` false. Giving a review anywhere takes the target out of the pool. Replacing a sample review with one from elsewhere makes it `from_sample` false, so it stops counting.
- **Agreement.** Counted when read, over reviews with `from_sample` true and the given Evaluation Model: reviews, agreed, false passes and false fails, overall and per check kind, with the rate's Wilson interval (the existing function) and Low sample under 30. The card shows the current Evaluation Model and lists earlier ones that have reviews.
- **Never an override.** Nothing that counts Verdicts or Live Verdicts (the Evaluation score, Regressions, the Publish summary, the Live score, the Live score drop alert, Suggestion evidence) reads reviews.
- **Retention.** The Purge pass that clears a Live Verdict's reasons also clears the reason on its reviews and stamps them purged-at. Outcomes stay, so agreement is unchanged. Deleting a Conversation goes through the same path. Reviews on Evaluation Run Verdicts follow their Run and are deleted with it.
- **Audit.** Reviews aren't Audit Events. They change nothing that Audit Events protect, and there will be many of them.
- **API.**
  - Organisation: get the next Review sample item, submit a review for it, and read Evaluation Model agreement (current and earlier Evaluation Models) and review counts.
  - Run results: each judged Verdict gains its review (outcome, reason, who, when, from_sample), and put and delete a review on it.
  - Trace: each Live Verdict check gains its review, and put and delete a review on it.
  - Everything flows into the OpenAPI schema and the generated client.
- **Permissions.** Editors and Owners give, replace and remove reviews and use the Review sample. Every Member reads reviews and agreement.
- **Studio UI (Tidepool throughout).**
  - **Review sample page:** at Organisation level, reached from the agreement card. It shows one item, the pass and fail buttons, Skip, then the reveal with the optional reason field when the Editor differed, and Next.
  - **Organisation settings (Models):** the agreement card beside the Evaluation Model, with the rate and interval, false passes and false fails, per-check rows, Low sample, earlier Evaluation Models and the link to the Review sample.
  - **Run detail and Trace:** agree and disagree controls on each judged Verdict and Live Verdict check, the reason field on disagree, and the existing review with who, when and "from the Review sample".
- **Fakes and the demo.** The fake judge is unchanged. The seed submits about 40 Review sample reviews through the API (ADR-0012) across the HR helper's Run Verdicts and Live Verdicts, a few of them false passes with reasons.
- **Glossary.** Verdict review, Review sample and Evaluation Model agreement are in `GLOSSARY.md`.

## Testing Decisions

- **Good tests** drive reviewing through the HTTP API, as the Studio does, and assert on responses and on agreement read back through the API.
- **No new seams.** Spec 18 uses the shared seams in [the specs README](./README.md#shared-test-seams). Verdicts and Live Verdicts come from spec 14's and spec 15's flows with scripted `FunctionModel`s on the **chat model** port. The random draw is seeded through test settings, as spec 15's sampling draw is, not faked behind a port.
- **API seam (primary):**
  - The pool: judged Reference answer and grounding Verdicts and both Live Verdict checks are served; Expected source, Fallback, Stale, Error, skipped and purged ones never are; reviewed ones aren't; another Evaluation Model's aren't.
  - Blindness: `next` never returns the Evaluation Model's outcome or reason; submitting returns them.
  - Agreement: agreed, false pass and false fail counts, per check, the Wilson interval and Low sample; reviews from elsewhere don't count; replacing a sample review from elsewhere stops it counting; per Evaluation Model after the Evaluation Model changes.
  - One review per target, replace and remove.
  - Never an override: the Evaluation score, Regressions, the Publish summary, the Live score and Suggestion evidence are the same with and without reviews.
  - Permissions and Organisation isolation.
- **Task seam:** the Purge clears reasons on Live Verdict reviews and keeps their outcomes, and agreement is unchanged. Deleting a Conversation does the same at once.
- **Frontend network seam (MSW):** the Review sample flow (blind, reveal, reason, skip, empty), the agreement card in each state, and the review controls in Run detail and the Trace, with accessibility checks.
- **End-to-end seam:** on the seeded stack, review a Review sample item, see the reveal, and see the agreement count go up. The axe checks cover the Review sample page.
- **Seed tests:** the existing seed tests extended to check the seeded reviews and that agreement shows false passes.
- **Prior art:**
  - Spec 14's Run results and Publish summary tests.
  - Spec 15's Live Verdict, Trace and Purge tests, and its seeded sampling draw.
  - The Version KPI tests for Wilson intervals and Low sample.

## Out of Scope

- **Improving the Evaluation Model ([spec 19](./19-judging-guidance-spec.md)):** using Verdict reviews to change how the Evaluation Model judges.
- Verdict reviews shaping Suggestions evidence, or changing any Verdict, score or alert.
- Agreement measured against Message Feedback or Conversation Ratings.
- Several reviewers per Verdict, or agreement between reviewers.
- Reviewing Expected source or Expect Fallback Text Verdicts.
- Sampling rules other than uniform random (by Agent, by check, more failures).
- Cohen's kappa or other chance-corrected measures.
- Agreement per Agent or per Project.

## Further Notes

- **Why blind.** Showing the Evaluation Model's pass or fail first anchors the Editor towards it and overstates agreement. Elsewhere the Verdict is already on screen, so those reviews are agree or disagree and kept out of the measure.
- **Why reviews never override.** If a disagree replaced the Verdict, every reviewed Verdict would agree by definition and the measure would mean nothing. It would also let an Editor clear an inconvenient Regression, which spec 14's "warn, never block" was written to avoid.
- **Skip is a small bias.** Skipped items stay in the pool, so the hardest judgements may be under-reviewed. A skip is better than a guess, and the skip count is shown so the bias is visible.
- **Live checks will outnumber Run Verdicts** in the pool once Live sampling is on. That is intended: Live Verdicts are the ones trusted without anyone watching.
- **No kappa.** On tens of reviews with most Verdicts passing, kappa swings wildly and few Editors can read it. False passes and false fails say the same thing in words.
- **Tickets:** to be written under `docs/tickets/18-verdict-review/`.
