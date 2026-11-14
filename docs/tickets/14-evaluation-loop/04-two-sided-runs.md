# 04: Two-sided Runs

**Ticket:** `14-04` · **Spec:** [Evaluation loop](../../specs/14-evaluation-loop-spec.md)

**What to build:** From an Evaluate dialog, an Editor compares two sides, the Live Version against the Draft by default or any two of the Draft and the Agent's Versions, answered at the same moment against the same Knowledge Base, and reads each side's Evaluation score with Regressions listed first.

**Blocked by:**
- [14-02: Evaluation tracer: one case, the Draft alone, one judged answer](02-evaluation-tracer.md)

**Status:** ready-for-agent

- [ ] A Run has a first and a second side, each the Draft or a Version; the default is the Live Version against the Draft, and the Draft alone for an Agent that has never been Published
- [ ] A Version side answers with the Instructions it pins; the Draft side with the Instructions Version or Instructions Draft chosen in the dialog, the Current Instructions Version by default; each side's effective AgentConfig and Instructions are snapshotted on the Run
- [ ] Both sides answer every case within the same Run, each with its own Retrieval Mode and models, through the real Guardrails
- [ ] Run detail shows each side's Evaluation score, then Regressions (pass on the first side, fail on the second), then improvements, then the rest, each case showing both sides' answers and Verdicts
- [ ] A Run with a Draft side is marked stale once the Draft has a newer Draft revision
- [ ] A side whose Provider Credential is gone is refused at start with the reason
- [ ] An Agent has at most one queued or running Run; a second start is refused with a conflict and Evaluate is disabled meanwhile
- [ ] A running Run can be cancelled; it stops between answers and keeps what it spent
- [ ] The Evaluation view lists the Agent's Run history with status, sides, scores and when it ran
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
