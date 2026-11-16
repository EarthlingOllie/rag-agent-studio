# 07: Demo seed, end-to-end and live suite

**Ticket:** `16-07` · **Spec:** [Suggestions](../../specs/16-suggestions-spec.md)

**What to build:** The Demo Organisation's HR helper shows a finished Suggestion with its check, a Knowledge Base gap and purged evidence; an end-to-end test applies a new Suggestion and sees Publish ask for a new Run; a nightly live run proves real proposing works.

**Blocked by:**
- [15-07: Demo seed, end-to-end and live suite](../15-live-evaluation/07-demo-seed-e2e-live.md)
- [16-03: All evidence, retrieval changes and Knowledge Base gaps](03-all-evidence-retrieval-gaps.md)
- [16-05: The check against the Evaluation Set](05-check-against-evaluation-set.md)
- [16-06: Applying a Suggestion to the Draft](06-apply-to-draft.md)

**Status:** ready-for-agent

- [ ] The seed adds one finished Suggestion for the HR helper from v2's failed Live Verdicts while v2 was Live, through the API under the seed clock (ADR-0012), with a checked system prompt change, a Knowledge Base gap and evidence old enough to be Purged; it reads as stale because v1 replaced v2
- [ ] Seed tests check the Suggestion, its check Run and its purged evidence
- [ ] End-to-end: on the seeded stack, open the seeded Suggestion and see its check, gap and "Text purged" evidence; start a new Suggestion run, apply it to the Draft, and see the Publish dialog ask for a new Evaluation Run; axe checks cover the Suggestions tab and Suggestion detail
- [ ] Live suite: one real-provider Suggestion run over the seeded evidence, nightly outside the coverage gate, asserting only that the output validates
- [ ] `docs/demo.md` gains a Suggestions step
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
