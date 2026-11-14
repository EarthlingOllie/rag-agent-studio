# 11: Demo seed, end-to-end and live suite

**Ticket:** `14-11` · **Spec:** [Evaluation loop](../../specs/14-evaluation-loop-spec.md)

**What to build:** The Demo Organisation's HR helper shows the whole loop, an end-to-end test walks from a seeded thumbs-down to a Regression in the Publish dialog, and a nightly live Run proves real judging works.

**Blocked by:**
- [14-06: Building the set: add from a Message, copy, cap and filters](06-build-set-from-messages.md)
- [14-08: Run Cost: estimate, actual, Organisation cost](08-run-cost.md)
- [14-09: Evaluation in the Publish dialog](09-publish-dialog-evaluation.md)

**Status:** ready-for-agent

- [ ] The seed gives the HR helper an Evaluation Set of about 12 cases, some added from seeded thumbs-down Messages through the API, at least one Expect Fallback Text case and one with an Expected source
- [ ] The seed runs two Runs judged by the fake Evaluation Model under the seed clock: v2 against v1, with Regressions that explain the revert, and the Draft against v3; the seed tests check both
- [ ] The Five-minute demo script and the Seeded history description mention the Evaluation view
- [ ] End-to-end: open a seeded thumbs-down in the Conversations viewer, add it to the HR helper's set with a Reference answer, change the Draft, Evaluate, and see the Regression in the Publish dialog; axe checks cover the Evaluation view and the Publish dialog
- [ ] Live suite: one real-provider Run of three cases (one per expectation kind) against the seed Knowledge Base, judged by a real model, nightly, outside the coverage gate
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
