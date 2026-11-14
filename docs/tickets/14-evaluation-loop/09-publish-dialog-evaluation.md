# 09: Evaluation in the Publish dialog

**Ticket:** `14-09` · **Spec:** [Evaluation loop](../../specs/14-evaluation-loop-spec.md)

**What to build:** The Publish dialog shows whether the Draft has been evaluated against the current Live Version with the Instructions being published, warns about Regressions or a lower Evaluation score, offers Evaluate, and never blocks Publishing.

**Blocked by:**
- [14-03: Evaluation Model, Evaluation repeats and combining results](03-evaluation-model-repeats.md)
- [14-04: Two-sided Runs](04-two-sided-runs.md)

**Status:** ready-for-agent

- [ ] A summary read, given the Instructions Version chosen in the dialog, returns one of `no_set`, `no_run`, `stale`, `live_changed`, `instructions_differ`, `regressions` or `clear`, with the latest qualifying Run's scores and Regressions; only Runs of the Draft against the current Live Version qualify
- [ ] The dialog's Evaluation section shows the warning with each Regression and its Verdicts' reasons, a notice for no Run, stale, Live changed or Instructions differ ("evaluated with Instructions v3, publishing with v2"), or a one-line hint to create a set when there is none
- [ ] An Evaluate action in the section starts a Live-against-Draft Run with the dialog's Instructions and shows its progress
- [ ] The Publish button stays enabled in every state, and Publishing succeeds in every state; the Publish API is unchanged
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
