# 02: Evaluation tracer: one case, the Draft alone, one judged answer

**Ticket:** `14-02` · **Spec:** [Evaluation loop](../../specs/14-evaluation-loop-spec.md)

**What to build:** In a new Evaluation Agent view, an Editor writes an Evaluation Case with a Reference answer, presses Evaluate, watches a Draft-only Evaluation Run progress, and reads the answer, its Trace, and the Reference answer and grounding Verdicts with the judge's reasons.

**Blocked by:**
- [14-01: Prefactor: one public way to resolve an AgentConfig's models](01-prefactor-resolve-agent-models.md)

**Status:** ready-for-agent

- [ ] Evaluation Case (question, Reference answer) with create, list, read, update and delete through the API, scoped to the Agent and its Organisation; a case without an expectation is refused
- [ ] Evaluation Run, Run side, case result and Verdict are stored; a Run snapshots each case's question and expectations when it starts
- [ ] Starting a Run enqueues a Celery task that answers each case once with the Draft and the Current Instructions Version through the Guardrail pipeline's `run_turn` and the real retrieval, creating no Conversation and no Message; Version KPIs, Usage rollups and the Token Budget are unchanged afterwards
- [ ] Each answer is judged once by the Default Model through the Model gateway (structured output, temperature 0, its own timeout), giving `reference_answer` and `grounding` Verdicts with one-sentence reasons; the answer and cited Chunks are passed as spotlighted data (prompt contract test); an answer that is the Fallback Text skips grounding
- [ ] The default fake chat model and the Demo model gain a deterministic judging path that can fail (Reference answer passes on a scripted key phrase; grounding passes when a Chunk is cited)
- [ ] Run status and progress are readable and the Studio polls them while the Run is queued or running
- [ ] The Evaluation Agent view is the fifth tab, between Versions and Embed & limits: the Evaluation Set list, a case editor (question and Reference answer), an Evaluate action, and Run detail with each answer, its Verdicts and reasons, and the Trace drawer
- [ ] Editors and Owners can manage cases and start Runs; another Organisation's Agents are unreachable; starting a Run on an archived Agent is refused, and its set stays readable
- [ ] Permanent deletion of an Agent removes its Evaluation Set and Runs
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
