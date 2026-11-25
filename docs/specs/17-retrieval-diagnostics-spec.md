# Spec 17: Retrieval diagnostics

**Status:** ready-for-agent · **Builds on:** [Spec 13](./13-agentic-retrieval-spec.md), [Spec 14](./14-evaluation-loop-spec.md)

## Problem Statement

Spec 14's Evaluation Runs say whether each case passed, and an Expected source's Verdict says whether the answer cited the right passage. They don't say *where* a failure happened:

- **Retrieval or answer?** An Expected source fails when it isn't cited. That is the same Verdict whether retrieval never found the passage, found it but left it out, or handed it to the model, which ignored it. These need opposite fixes: Top-k, Minimum Score or Hybrid weighting in the first two cases, system prompt wording in the third.
- **Nothing across the set.** Each case shows its own Verdicts. Nothing says how often a side found, gave or cited its Expected sources overall, so a change that improves wording while making retrieval worse can look like a wash.
- **The cut is invisible.** The Trace keeps the Chunks retrieval left out and why, but nobody reads twenty Traces to notice that the right passage keeps arriving at rank 7 while Top-k is 5.
- **The stored rank can't answer it.** The rank in the Trace is the number in a Chunk's label. It is empty for Chunks that weren't given to the model, and in Agentic Retrieval Mode it keeps counting across Searches, so a passage's position in retrieval's own order is lost for exactly the passages that were cut.

## Solution

Every Evaluation Run gains **Retrieval diagnostics**: for each side, how far retrieval got with the Expected sources, and where failures sit.

- **Three stages per Expected source in each answer.** **Found** (retrieval returned a Chunk holding it, at any rank, in any Search), **Given** (that Chunk went to the model) and **Cited** (the answer cited it, which is the Verdict as it is today). A source Found but not Given shows the reason from its Trace: below the Minimum Score, outside Top-k, outside the Agent's Tags or flagged by a Guardrail.
- **Found rank.** An Expected source's best rank in retrieval's own order in any Search of the answer. From now on retrieval's rank is stored for every Chunk in the Trace, given or not.
- **Rates per side.** The **Found rate**, **Given rate** and **Cited rate**, each "x of y" over every Expected source in every answer, and the **median Found rank** beside how many sources weren't Found. Both sides sit next to each other with the Better side marked and "(small sample)" under 30.
- **Retrieval breakdown.** Each side's answers sorted into four cells by whether every Expected source was Given and whether the answer's other Verdicts passed: **Clean pass**, **Answer miss**, **Retrieval miss** and **Passed without source**.
- **Display only.** Verdicts, the Evaluation score, Regressions and the Publish warning don't change.
- **The demo tells the story.** The HR helper's seeded Run has a case whose Expected source is Found at rank 7 and left out by Top-k 5.

## User Stories

### Per case

1. As an Editor, I want each Expected source in each answer marked Found, Given and Cited, so that I see how far retrieval got with it.
2. As an Editor, I want an Expected source that was Found but not Given to show why it was left out (below the Minimum Score, outside Top-k, outside the Agent's Tags or flagged by a Guardrail), so that I know which setting to change.
3. As an Editor, I want each Expected source's Found rank, so that I see how close it came to being given to the model.
4. As an Editor, I want the Found rank to be retrieval's own position, not the Chunk label number, so that a left-out passage still has a rank.
5. As an Editor, I want the Found rank in Agentic Retrieval Mode to be the best rank across the answer's Searches, so that refining a query isn't counted against the Agent.
6. As an Editor, I want an Agentic answer that made no Search, or whose Searches the Search limit refused, to count its Expected sources as not Found, so that deciding not to search shows as a retrieval failure.
7. As an Editor, I want a Fallback Text answer counted like any other, so that a source cut by the Minimum Score shows with that reason.
8. As an Editor, I want each repeat's stages shown, so that a source Found in two repeats out of three is visible.
9. As an Editor, I want Stale expectations left out of every stage, so that Knowledge Base changes aren't counted as retrieval failures.

### Per side

10. As an Editor, I want each side's Found rate, Given rate and Cited rate as "x of y", so that I see where Expected sources are lost across the whole set.
11. As an Editor, I want every Expected source in every answer to count once, so that unsteady retrieval isn't hidden by a majority.
12. As an Editor, I want each side's median Found rank beside how many Expected sources weren't Found, so that I can compare it with Top-k.
13. As an Editor, I want answers the input Guardrail blocked before retrieval left out of the rates and counted beside them, so that a block isn't counted as a retrieval failure.
14. As an Editor, I want answers with an Error left out, so that a provider outage doesn't look like a retrieval failure.
15. As an Editor, I want the two sides' rates next to each other with the Better side marked, so that I see which configuration retrieves better.
16. As an Editor, I want a rate marked "(small sample)" when either side checked fewer than 30 Expected sources, so that a handful of cases doesn't look decisive.
17. As an Editor, I want a lower median Found rank marked as the Better side, so that the direction is clear.
18. As an Editor, I want a side with no Expected sources to say so instead of showing empty rates, so that a set of Reference-answer cases isn't confusing.

### Retrieval breakdown

19. As an Editor, I want each side's answers to cases with an Expected source sorted into Clean pass, Answer miss, Retrieval miss and Passed without source, so that I can tell retrieval failures from answer failures at a glance.
20. As an Editor, I want an answer to count as Given only when every one of its non-stale Expected sources was Given, so that a case that needs two Documents needs both.
21. As an Editor, I want "passed" in the breakdown to mean every other Verdict of the answer passed (Reference answer and grounding), so that the Expected source Verdict doesn't count twice.
22. As an Editor, I want to open the answers in any cell, so that I can read the Retrieval misses or the Answer misses together.
23. As an Editor, I want Passed without source explained as "the Expected source may be too narrow, or another passage covers it", so that I fix the case rather than the Agent when that's the problem.

### Runs, history and Publishing

24. As an Editor, I want Retrieval diagnostics on Rollout evaluations too, so that an Instructions rollout's retrieval is visible.
25. As an Editor, I want Runs from before this spec to show the stages, rates and breakdown, with "—" for the Found rank, so that my history stays useful.
26. As an Editor, I want Retrieval diagnostics never to change Verdicts, the Evaluation score, Regressions or the Publish warning, so that the same failure isn't counted twice.
27. As an Editor, I want an in-progress Run's diagnostics to fill in as answers arrive, so that I see them without waiting for the end.

### Permissions, demo and accessibility

28. As a Member, I want to see Retrieval diagnostics wherever I can see a Run, so that everyone reads the same evidence.
29. As a Member of another Organisation, I must never see another Organisation's Runs or their diagnostics.
30. As a prospective customer watching the demo, I want the HR helper's Run to show an Expected source Found at rank 7 and left out by Top-k 5, so that I see the Studio point at the setting to change.
31. As a keyboard or screen-reader user, I want the rates, the breakdown and the per-source stages to be readable as text and operable from the keyboard, so that the diagnostics don't depend on colour or a mouse.

## Implementation Decisions

- **Where it lives.** Retrieval diagnostics are counted by the `evaluation` module when a Run's results are read. The `retrieval` module and the Trace builders only gain the stored rank. Nothing new reaches into another module's tables.
- **Schema.**
  - **Message retrieval:** a new nullable `retrieval_rank`: the Chunk's rank in retrieval's own order within its Search (from 1), for Chunks given to the model and Chunks left out alike. Null for rows written before this spec. No backfill.
  - **Trace payload:** each traced Chunk gains `retrieval_rank` (nullable). Evaluation Run results already store each answer's Trace as JSON, so new Runs carry it and old ones read it as null.
  - No new tables. Nothing about the diagnostics is stored; they are counted from the stored Traces and Verdicts each time a Run is read.
- **Stored rank.** Retrieval already ranks its candidates from 1 before the Minimum Score, Tags, Top-k and Guardrail cuts. That rank is what's stored, whether or not the reranker reordered them (it is the order after reranking when a reranker ran). In Agentic Retrieval Mode each Search's ranks start at 1.
- **Counting the stages.**
  - An Expected source's passage is matched against the Chunk text in the answer's stored Trace with the same rule the Expected source Verdict uses (ignoring case and whitespace). The Chunks considered are the up-front Chunks in Automatic Retrieval Mode and every Search's Chunks in Agentic.
  - **Found:** a Trace Chunk holds it. **Given:** a Chunk holding it has a label rank. **Cited:** its Verdict passed.
  - **Found rank:** the lowest `retrieval_rank` among Chunks holding it. Null when not Found or when the Trace predates the stored rank.
  - **Left-out reason:** for a source Found but not Given, the excluded reason of its best-ranked holding Chunk.
  - Stale expectations, answers with an Error and answers the input Guardrail blocked are left out. Blocked answers are counted per side. An answer whose Agentic Searches were all refused, or that made none, counts its sources as not Found.
- **Rates and the median.** Per side: Found, Given and Cited as counts over every checked Expected source in every answer (each repeat counts). The median Found rank is taken over sources that were Found and have a rank, beside the not-Found count. Better side: higher rates, lower median. "(small sample)" when either side checked fewer than 30 Expected sources.
- **Retrieval breakdown.** Per side, over answers with at least one checked Expected source: Given means every checked source was Given; passed means every other non-stale Verdict passed. Every answered case has a grounding Verdict, so passed is always defined.
- **API.**
  - The Run results response gains, per side, a `retrieval` block: the three counts and total, the median Found rank, the not-Found count, the blocked count, the four breakdown counts, and per metric the Better side and small-sample flag.
  - Each case result gains, per Expected source, `found`, `given`, `cited`, `found_rank` and `left_out_reason`.
  - The Trace payload gains `retrieval_rank` per Chunk.
  - Everything flows into the OpenAPI schema and the generated client.
- **Studio UI (Tidepool throughout).**
  - **Run detail:** a "Retrieval" section above the case list, with the two sides' rates and median next to each other, the Better side marked as in the Version comparison, and each side's breakdown as a labelled 2×2 whose cells filter the case list.
  - **Case rows:** each Expected source shows its stages as text, for example "Found #7 · left out: outside Top-k · not cited", per repeat.
  - The Trace drawer is unchanged apart from carrying the new field.
- **Fakes and the demo.** The fake retrieval path already returns ranked candidates, so the stored rank needs no fake change. The seed arranges one HR helper case whose Expected source sits below Top-k, so its seeded Run shows "Found #7 · left out: outside Top-k". The seed still goes through the API (ADR-0012).
- **Glossary.** Found, Given, Cited, Found rank and Retrieval breakdown are in `GLOSSARY.md`.

## Testing Decisions

- **Good tests** drive Runs through the HTTP API, as the Studio does, and assert on the Run results response. They don't assert on how the diagnostics are counted internally.
- **No new seams.** Spec 17 uses the shared seams in [the specs README](./README.md#shared-test-seams). Answers and judging come from scripted `FunctionModel`s on the **chat model** port, and retrieval runs for real against the hash **embedder**.
- **API seam (primary):**
  - Stages: Found, Given and Cited; Found but left out for each excluded reason; not Found; Stale left out.
  - Agentic: best rank across two Searches; no Search; every Search refused by the Search limit.
  - Answers left out: an input Guardrail block (counted as blocked) and an Error.
  - Rates over repeats, the median Found rank with the not-Found count, the Better side and small sample, and a side with no Expected sources.
  - The four breakdown cells, including a case with two Expected sources where only one was Given.
  - A Run result whose stored Trace has no `retrieval_rank` gives stages and rates with a null Found rank.
  - Verdicts, the Evaluation score, Regressions and the Publish summary are unchanged by the new fields.
  - Organisation isolation holds.
- **Retrieval and Trace:** the stored rank for given and left-out Chunks in both Retrieval Modes, read back through the Playground Trace.
- **Frontend network seam (MSW):** the Retrieval section with both sides, the Better side and small-sample marks, the breakdown cells filtering the case list, per-source stages per repeat, the old-Run "—", and accessibility of the new section.
- **End-to-end seam:** on the seeded stack, open the HR helper's Run and see the "Found #7 · left out: outside Top-k" source and the breakdown. The axe checks cover Run detail.
- **Seed tests:** the existing seed tests extended to check the seeded Run's diagnostics.
- **Prior art:**
  - Spec 14's Run results tests (Verdicts, Stale, Error, repeats).
  - The Version comparison tests for the Better side and "(small sample)".
  - Spec 13's Agentic Trace tests (Searches, the Search limit).

## Out of Scope

- **Retrieval signals on Visitor replies.** Live traffic has no Expected sources. The first follow-up would be proxies such as top relevance, the Fallback rate and replies with no Citation. A judged context-relevance check would reopen spec 15's limit on Live Verdict checks.
- MRR, recall@k or any metric named by k, since Top-k differs between sides.
- A Publish warning or Regression from retrieval, and any change to how Verdicts are worked out.
- Backfilling `retrieval_rank` for answers made before this spec.
- Showing `retrieval_rank` in the Playground or Conversations Trace drawer.
- Diagnostics across Runs (a trend over an Agent's Run history).

## Further Notes

- **Why Found and Given, not recall.** "Recall at Top-k" means something different on each side when the sides have different Top-k. Found and Given name what happened, and the difference between them is the cut an Editor controls.
- **Why per answer.** The Evaluation score takes a majority per case, which is right for pass or fail but would hide a passage retrieval finds only sometimes, the most common Agentic retrieval problem.
- **Passed without source** is often a case problem, not an Agent problem: another passage says the same thing, or the Expected source is narrower than the answer needs. Saying so stops Editors tuning the Agent to satisfy a bad case.
- **Tickets:** to be written under `docs/tickets/17-retrieval-diagnostics/`.
