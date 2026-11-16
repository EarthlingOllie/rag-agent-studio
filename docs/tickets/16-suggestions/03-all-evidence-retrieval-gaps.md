# 03: All evidence, retrieval changes and Knowledge Base gaps

**Ticket:** `16-03` · **Spec:** [Suggestions](../../specs/16-suggestions-spec.md)

**What to build:** A Suggestion run reads every kind of evidence with its Trace, can propose retrieval changes that cite their evidence, reports Knowledge Base gaps, and can conclude that nothing should change; purged evidence stays readable as "Text purged".

**Blocked by:**
- [16-02: Suggestion tracer: failed Live Verdicts become a system prompt Suggestion](02-suggestion-tracer.md)

**Status:** ready-for-agent

- [ ] Evidence also includes the Live Version's replies with a thumbs-down (with comments) and replies in Conversations whose current Conversation Rating is 1 or 2, plus Evaluation Case results that failed on a side running the Live Version in the latest finished Evaluation Run with such a side
- [ ] Each reply's evidence includes its Remembered turns, its Live Verdict reasons or Feedback, and a compact Trace (Searches, Message retrievals with Relevance and cited flags, excluded Chunks and why)
- [ ] A reply that qualifies several ways counts once with all its reasons; Purged replies and other Versions' replies are left out; at most the 50 most recent pieces are used and the count before the cap is stored
- [ ] Changes to `retrieval.top_k`, `retrieval.minimum_score` and `retrieval.hybrid_weighting` are accepted when within the setting's valid range and citing at least one piece of evidence; others are dropped; the prompt receives each setting's valid range
- [ ] Knowledge Base gaps (topic and explanation in the run's own words, with evidence links) are stored and shown with a link to the Project's Knowledge Base; they never count as a change
- [ ] Outcomes `changes`, `gaps_only` ("No configuration change") and `no_change` ("No change suggested", with the reasoning) are stored and shown
- [ ] The fake and Demo model's proposing path also lowers the Minimum Score by 0.05 citing evidence with a Chunk excluded within 0.05 of it, and reports a gap for each failed Live Verdict whose reply cited no Chunk
- [ ] After the Purge, evidence reads "Text purged" with the reply's date and Live Verdict, and the changes and explanation are intact; evidence from a deleted Evaluation Case reads "Case deleted"
- [ ] Evidence chips for Evaluation Cases open the case result in Run detail
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
