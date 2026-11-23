# Spec 19: Judging guidance

**Status:** ready-for-agent · **Builds on:** [Spec 14](./14-evaluation-loop-spec.md), [Spec 15](./15-live-evaluation-spec.md), [Spec 16](./16-suggestions-spec.md), [Spec 18](./18-verdict-review-spec.md) · **Decisions:** [ADR-0016](../adr/0016-evaluation-cases-outlive-retention.md)

## Problem Statement

Spec 18 measures how often the Evaluation Model agrees with Editors, and records why they disagree. It doesn't change anything:

- **Known disagreements keep happening.** If Editors keep saying "a partial answer that says what it doesn't cover should pass 'answers the question'", every new Live Verdict still fails such answers, and the Live score stays understated.
- **The only lever is the Evaluation Model.** An Owner can switch to another model, which changes everything at once and may fix nothing. There is no way to tell the Evaluation Model what *this* Organisation means by a pass.
- **A change can't be checked.** Nothing says whether a change to judging makes agreement better or worse before every Verdict starts using it.
- **Comparisons would break silently.** Anything that changes how Verdicts are judged also changes Evaluation scores, the Live score and the Live score drop alert. Comparing judgements made before and after such a change would blame the Agent for the judge's change.

## Solution

Owners give the Evaluation Model **Judging guidance**: the Organisation's own instructions, added to every judgement. The Evaluation Model can draft it from Editors' disagreements, the draft is checked on reviews it didn't see, and an Owner saves it. The **Judging setup** (Evaluation Model plus guidance version) is recorded on every judgement so that only like is compared with like.

- **Guidance.** One text per Organisation, up to 2,000 characters, in Organisation settings › Models. Each save is a new version and an Audit Event. Owners write and save it; Editors can read it.
- **Draft from disagreements.** Once there are at least 10 disagreements and 30 Review sample reviews under the current Judging setup, an Owner can ask the Evaluation Model to draft guidance. It reads the Verdicts Editors disagreed with and their reasons, from every review made outside the Review sample plus a random half of the Review sample reviews, and proposes guidance with a short explanation.
- **Check before saving.** The draft re-judges the other half of the Review sample reviews, which it never saw, and shows "would agree on x of y (now z)". An Owner can edit the text and check again, or check guidance they wrote by hand. A drop in agreement warns; it never blocks saving.
- **Judging setup on every judgement.** Every Verdict, Live Verdict, Evaluation Run and Verdict review keeps the Judging setup it was judged under. Evaluation Model agreement and the Review sample work per Judging setup. The Live score drop alert compares only Live Verdicts judged under the same Judging setup. The Version comparison and Time series say when a range mixes Judging setups.
- **A person always decides.** Guidance is never saved without an Owner, and reviews never reach the judging prompt as examples.

## User Stories

### Writing and saving guidance

1. As an Owner, I want to write Judging guidance in Organisation settings › Models, so that the Evaluation Model follows our idea of a pass.
2. As an Owner, I want guidance to apply to every judgement in the Organisation, Evaluation Runs and Live Verdicts alike, so that scores stay comparable across Agents.
3. As an Owner, I want guidance limited to 2,000 characters, so that it stays focused and cheap to send with every judgement.
4. As an Owner, I want every save to be a new version with who saved it and when, so that I can see how judging changed.
5. As an Owner, I want each save recorded as an Audit Event, so that a change in scores can be traced to it.
6. As an Owner, I want to remove guidance, so that I can go back to the Evaluation Model's own judgement.
7. As an Editor, I want to read the current guidance and its versions, so that I know how Verdicts are judged.
8. As an Editor, I don't want to change guidance, so that how the whole Organisation is judged stays with Owners.

### Drafting from disagreements

9. As an Owner, I want the Evaluation Model to draft guidance from the Verdicts Editors disagreed with and their reasons, so that I don't have to read every disagreement myself.
10. As an Owner, I want drafting offered only once there are at least 10 disagreements and 30 Review sample reviews under the current Judging setup, so that a draft isn't built on a handful of opinions.
11. As an Owner, I want the Draft button to say what is missing when drafting isn't offered yet, so that I know how many more reviews are needed.
12. As an Owner, I want to see the estimated Cost before drafting, so that I decide knowing what it spends.
13. As an Owner, I want the draft to come with a short explanation of which disagreements each part answers, so that I can judge whether it is right.
14. As an Owner, I want the draft to be general rules, not quotes from replies, so that guidance never carries Visitor text.
15. As an Owner, I want to edit the draft before saving, so that I stay in charge of the wording.
16. As an Owner, I want to cancel a draft in progress, so that a mistaken request stops spending.
17. As an Owner, I want at most one draft or check in progress in the Organisation, so that two Owners don't spend twice.
18. As an Owner, I want drafting and checking Cost in Organisation cost, never against the Evaluation budget, so that it can't pause Live sampling.

### Checking a draft

19. As an Owner, I want a draft checked on Review sample reviews it never saw, so that the result isn't flattered by its own inputs.
20. As an Owner, I want to see "would agree on x of y (now z)" with false passes and false fails, so that I know what saving it would do.
21. As an Owner, I want the check marked Low sample under 30 held-out reviews, so that I don't over-read a small check.
22. As an Owner, I want Live Verdicts whose reply was Purged left out of the check, so that nothing is re-judged without its text.
23. As an Owner, I want to check guidance I wrote by hand, and to check again after editing a draft, so that every version can be tested before it is saved.
24. As an Owner, I want a warning when a check shows lower agreement, and to save anyway, so that a noisy check never stops me.
25. As an Owner, I want a check marked out of date once I edit the text, so that I don't save on a stale number.

### Judging setup and comparisons

26. As an Owner, I want every Verdict, Live Verdict, Evaluation Run and Verdict review to record its Judging setup, so that I always know what judged it.
27. As an Owner, I want Evaluation Model agreement shown for the current Judging setup, with earlier ones listed, so that I see whether new guidance helped.
28. As an Editor, I want the Review sample to serve only judgements under the current Judging setup, so that new reviews measure the judging in use.
29. As an Owner, I want the Live score drop alert to compare only Live Verdicts judged under the same Judging setup, so that saving guidance can't raise a false alarm.
30. As an Editor, I want the Version comparison and Time series to note when their range mixes Judging setups, with a marker where it changed, so that I don't blame a Version for a change in judging.
31. As an Editor, I want the Publish dialog to note when the Draft's latest Run was judged under an earlier Judging setup, so that I know its scores may read differently now.
32. As an Editor, I want each Run to show the Judging setup it was judged under, so that history is clear.
33. As an Owner, I want changing the Evaluation Model to start a new Judging setup too, so that both kinds of change are treated the same.

### Permissions, demo and accessibility

34. As a Member of another Organisation, I must never see another Organisation's guidance, drafts or checks.
35. As a keyboard or screen-reader user, I want the guidance editor, the draft and check results and the Judging setup notes to be operable and announced, so that the feature is accessible.

## Implementation Decisions

- **Where it lives.** Guidance, drafting and checking extend the `evaluation` module, which owns the judge and the Evaluation Model. The Judging setup notes in the Version comparison and Time series and the alert's like-for-like rule extend `analytics`. Nothing new reaches into another module's tables.
- **Schema.**
  - **Judging guidance version:** Organisation, version number, text (up to 2,000 characters; empty means none), source (`written` or `drafted`), saved_by, saved_at, and the latest check result if any (held-out count, agreed, false passes, false fails, and the agreement it replaced).
  - **Organisation:** the current Judging guidance version (nullable).
  - **Judging setup:** recorded as the pair (Evaluation Model, guidance version) wherever the Evaluation Model is already copied: Evaluation Runs, Live Verdicts and Verdict reviews. Evaluation Verdicts read it from their Run.
  - **Guidance job:** one per request: kind (`draft` or `check`), status, the text checked, the held-out split (seeded and stored, so a re-check uses the same halves), the draft text and explanation, Cost, who asked, timestamps. At most one in progress per Organisation, under a lock on the Organisation.
- **Judging with guidance.** The judge adds the current guidance as an "Organisation guidance" section after its fixed instructions and before the spotlighted data blocks. Guidance is trusted text saved by an Owner, so it is an instruction, not data. It can't change the output schema or the rule that answers and Chunks are data. Every judgement records its Judging setup at the time it starts.
- **Drafting.**
  - Offered when the current Judging setup has at least 10 disagreeing reviews and at least 30 Review sample reviews. The held-out half is a seeded random half of the Review sample reviews.
  - The draft call gets the disagreeing reviews from outside the held-out half (the Verdict's check, the Evaluation Model's outcome and reason, the Editor's outcome and reason, and the question, answer and Chunks it judged, as spotlighted data) and the current guidance. It is told to write general rules without quoting replies. It returns guidance text within the limit and an explanation linking parts to the reviews they answer.
  - Purged Live Verdicts give only their outcomes and the Editor's outcome, since their text and reasons are gone.
  - The estimated Cost uses the Evaluation Model's prices for a fixed allowance per review read, as Suggestion runs do.
- **Checking.** Re-judges each held-out review's target with the candidate text and counts agreement with the Editor's outcome: agreed, false passes, false fails, Low sample under 30, beside the current Judging setup's agreement on the same reviews. Targets without text (Purged Live Verdicts) are left out. A check never creates or changes a Verdict or Live Verdict.
- **Saving.** An Owner saves the text, with or without a check. Saving creates a new version, makes it current, and records an `organisation.judging_guidance_changed` Audit Event with before and after. A check showing lower agreement adds a warning to the save dialog; it never blocks. Removing guidance saves an empty version.
- **Comparisons.**
  - **Agreement and the Review sample** (spec 18) work per Judging setup instead of per Evaluation Model.
  - **Live score drop alert:** the new Live Version's Live Verdicts and the previous Live Version's are taken under the current Judging setup only. If the previous Version has fewer than 30 under it, there is no alert, as spec 15 already does for too few Live Verdicts.
  - **Version comparison and Time series:** a note, in the Confounder note's style, when the range holds Live Verdicts under more than one Judging setup, and a marker on the Time series where it changed.
  - **Publish dialog:** a notice when the Draft's latest Run was judged under an earlier Judging setup, beside the existing stale notices. It is a notice, not a warning, and never blocks.
- **Cost.** Drafts and checks are frozen with the existing cost function and count in Organisation cost's Evaluation column, never against the Evaluation budget or the Token Budget.
- **API.**
  - Organisation settings: read guidance and its versions (every Member); save and remove (Owners); start a draft or a check, read its progress and result, cancel it (Owners); the drafting threshold and what's missing.
  - Run, Live Verdict and Verdict review payloads gain their Judging setup. Agreement responses are per Judging setup.
  - The Version comparison and Time series responses gain the Judging setup changes in their range. The Publish summary gains the earlier-Judging-setup notice.
  - Everything flows into the OpenAPI schema and the generated client.
- **Studio UI (Tidepool throughout).**
  - **Organisation settings (Models):** a Judging guidance card under the agreement card: the current text and version, version history, Edit (Owners), Draft with its threshold or estimate, Check, and the check result with its warning.
  - **Run detail:** the Judging setup in the Run header.
  - **Analytics:** the mixed Judging setup note and Time series marker.
  - **Publish dialog:** the earlier Judging setup notice.
- **Fakes and the demo.** The fake judge and the Demo model's judging path gain one guidance rule: when the guidance contains a scripted phrase, "answers the question" passes partial answers that say what they don't cover. That lets tests and the end-to-end run show a check raising agreement. The seed is unchanged; the demo Organisation has no guidance.
- **Glossary.** Judging guidance and Judging setup are in `GLOSSARY.md`.

## Testing Decisions

- **Good tests** drive guidance through the HTTP API, as the Studio does, and assert on responses and on judgements read back through the API. They don't assert on judge prompt strings, apart from extending spec 14's contract test to show the guidance section sits outside the spotlighted data and the draft call passes reviews as spotlighted data.
- **No new seams.** Spec 19 uses the shared seams in [the specs README](./README.md#shared-test-seams). The judge and drafter are the **chat model** port, scripted with `FunctionModel`. The held-out split is seeded through test settings.
- **API seam (primary):**
  - Saving: versions, Audit Events, removing, Owners only, Editors read.
  - Judging: new Runs and Live Verdicts use the current guidance and record their Judging setup; earlier judgements keep theirs.
  - Drafting: refused below each threshold with what's missing; the draft never sees held-out reviews; Purged Live Verdicts give outcomes only; one job at a time; cancel; Cost in Organisation cost and not the Evaluation budget.
  - Checking: agreement on held-out reviews with false passes and false fails; Purged targets left out; a re-check uses the same split; no Verdict or Live Verdict changes.
  - Comparisons: agreement and the Review sample per Judging setup; the Publish summary notice.
  - Organisation isolation holds.
- **Task seam:** the hourly alert compares only Live Verdicts under the current Judging setup, and saving guidance can't raise it; the draft and check jobs run eagerly.
- **Frontend network seam (MSW):** the guidance card in each state (no guidance, versions, threshold not met, drafting, check result with warning, check out of date after an edit), read-only for Editors, the Run header, the analytics note and marker, the Publish notice, and accessibility.
- **End-to-end seam:** on the seeded stack with enough reviews made through the Review sample, draft guidance with the fake judge, check it, see agreement rise, and save it. The axe checks cover the guidance card.
- **Live suite:** one real-provider draft and check over a small seeded set of reviews, run nightly outside the coverage gate.
- **Prior art:**
  - Spec 16's Suggestion run tests (an Owner-started model job with an estimate, cancel and Cost).
  - Spec 14's judge contract test and Evaluation Model change tests.
  - Spec 15's alert tests.
  - Spec 18's agreement tests.

## Out of Scope

- **Fine-tuning a model** on Verdict reviews. Deferred for this phase.
- **Reviewed examples in the judging prompt.** They would copy Message text outside `messages` (ADR-0016), cost tokens on every judgement and put Visitor text into the judging instructions.
- Guidance per Agent, per Project or per check.
- Re-judging past Verdicts or Live Verdicts under new guidance.
- Saving guidance automatically, or on a schedule.
- Drafts that also change the Evaluation Model.
- Seeding guidance in the demo Organisation.

## Further Notes

- **A person always decides.** As with Suggestions, the Evaluation Model only proposes. A failed check warns and never blocks, because held-out sets are small and judges are noisy.
- **Why a held-out half.** A draft written from a set of disagreements will almost always fix that set. Checking on reviews the draft never saw is the only way the number says whether it generalises. The cost is that half the reviews don't inform the draft.
- **Change guidance rarely.** Each save starts a new Judging setup: agreement and the Review sample start again for it, and the Live score drop alert stays quiet for a previous Live Version that has no Live Verdicts under it. The guidance card says so before saving.
- **Guidance must not carry Visitor text.** It is kept with no Retention Window. The draft is told to write general rules, and the Owner reviews it before saving. This is the same safeguard as a Suggestion's stored change and explanation.
- **Tickets:** to be written under `docs/tickets/19-judging-guidance/`.
