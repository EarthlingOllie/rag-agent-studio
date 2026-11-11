# Spec 13: Agentic retrieval

**Status:** ready-for-agent · **Builds on:** [Spec 04](./04-agents-retrieval-playground-spec.md), [Spec 08](./08-guardrails-evaluation-spec.md), [Spec 12](./12-reskin-fixes-sidebar-navigation-spec.md) (on `candidate-reskin`) · **Decision:** [ADR-0015](../adr/0015-read-only-knowledge-search-tool.md)

## Problem Statement

Today every Agent retrieves the same way. One Hybrid search runs on the Visitor's exact words, the best Chunks go to the model, and the model answers from those. That's cheap and predictable, but it falls short on the questions Visitors actually ask:

- A **multi-part question** ("what's the refund window, and does it apply to EU orders?") needs material on two topics. One search on the whole sentence finds one of them, or a blend of both that's mediocre.
- A **follow-up** ("and for Germany?") means nothing on its own. A search on those words finds nothing, so the Agent gives its Fallback Text even though the answer is in the Knowledge Base.
- A **vague or mis-worded question** finds weak Chunks, and the model can't try again with better terms.
- A **greeting or thank-you** still pays for a search and sends irrelevant Chunks to the model.

Editors can't fix this with the settings they have. Top-k, Hybrid weighting, the Minimum Score and the Reranker all tune a single search; none of them adds a second one. Some Agents also need accuracy more than they need a low cost per reply, and others the other way round, so Editors want to choose per Agent and measure what the choice costs.

## Solution

An Agent has a **Retrieval Mode**, set in the Retrieval section of its Draft:

- **Automatic**: today's behaviour. One Hybrid search on the Visitor input, then one model call.
- **Agentic**, the default for new Agents: the model is given one tool, **Knowledge Search**. It decides whether to search, how many times (up to the Agent's **Search limit**) and with what query. Each search runs exactly the retrieval an Automatic Agent would, with Tag scoping, the Minimum Score, the Reranker and Top-k all taken from the Agent's settings. The model controls only the query.

Because the Retrieval Mode is in AgentConfig, it's part of every Version. An Editor can publish an Agentic Version, compare it against the Automatic one before it, and see the differences in cost, thumbs-up rate, fallback rate, latency and searches per reply.

**In Agentic mode:**

- **The Playground** shows each Search as it happens ("Searching: *refund policy for EU orders*").
- **The widget** shows Visitors a short "Searching the knowledge base…" status, which Editors can reword.
- **The Trace** lists every Search in order, with its query and the Chunks it found, gave the model or excluded.
- **The Fallback Text stays guaranteed.** If the model searched and nothing relevant was found, Visitors get the Agent's Fallback Text, never an invented answer.
- **Guardrails still apply:**
  - Search queries are checked for the Canary token.
  - Chunks returned by Knowledge Search are spotlighted and Flagged Chunk handling applies, exactly as in Automatic mode.
  - The Attack evaluation suite runs in both modes.

## User Stories

1. As an Editor, I want to choose an Agent's Retrieval Mode (Automatic or Agentic) in its Draft, so that I can trade accuracy against cost for each Agent.
2. As an Editor, I want new Agents to start in Agentic mode, so that they give the most accurate answers unless I choose otherwise.
3. As an Editor, I want the Retrieval Mode control to explain the trade-off in a sentence (Agentic is more accurate and can cost more per reply; Automatic is cheaper and predictable), so that I can choose without reading documentation.
4. As an Editor, I want the Retrieval Mode saved by Autosave like every other Draft setting, so that it behaves like the rest of the editor.
5. As an Editor, I want the Retrieval Mode to be part of each published Version, so that Version comparison shows what switching modes did.
6. As an Editor, I want reverting an Agent to restore the Retrieval Mode its earlier Version had, so that a revert really is a full step back.
7. As an Editor, I want to set a Search limit (1–5, default 3) for an Agentic Agent, so that a single reply can't run up unbounded cost.
8. As an Editor, I want the Search limit hidden or disabled when the Agent is Automatic, so that I only see settings that apply.
9. As an Editor, I want Top-k, Hybrid weighting, the Minimum Score, Tag scoping and the Reranker to apply to every Search an Agentic Agent makes, so that I tune retrieval once for both modes.
10. As an Editor, I want saving a Draft in Agentic mode to be refused, with a clear reason, when the Agent's model (its Model override, or the Organisation's Default Model) can't use tools, so that I can't publish an Agent that can't work.
11. As an Editor, I want the model picker to show which models support Agentic mode, so that I can pick one that does.
12. As an Owner, I want an Agentic Agent to keep answering if the Default Model is later changed to one without tool support, by running as Automatic and saying so in the Trace, so that changing the Default Model never takes Agents offline.
13. As an Editor, I want an Agentic Agent to answer greetings and thanks without searching, so that small talk doesn't cost a retrieval.
14. As an Editor, I want an Agentic Agent to search before answering any question about the Knowledge Base, so that its answers are grounded rather than recalled from its training.
15. As an Editor, I want an Agentic Agent to search more than once in a reply when a question has several parts, so that each part is answered from the right material.
16. As an Editor, I want an Agentic Agent to turn a follow-up ("and for Germany?") into a complete search query using the Conversation so far, so that follow-ups are answered from the Knowledge Base.
17. As an Editor, I want an Agentic Agent to search again with different wording when a search finds nothing useful, so that phrasing doesn't decide whether a question gets answered.
18. As a Visitor, I want the Agent's Fallback Text when nothing relevant exists, even in Agentic mode, so that I'm never given an invented answer.
19. As an Editor, I want the Fallback Text decided before any of the answer is shown, so that Visitors never see an answer appear and then get replaced.
20. As an Editor, I want the model told to answer from what it has once the Search limit is reached, so that every reply still ends with an answer.
21. As an Editor, I want the Trace to say when a reply hit the Search limit, so that I can tell whether to raise it.
22. As an Editor, I want each Search to appear in the Playground as it happens, with the query the model wrote, so that I can follow how the Agent works out its answer.
23. As a Visitor, I want a short "Searching the knowledge base…" status while the Agent searches, so that a slower reply doesn't look stuck.
24. As a Visitor using a screen reader, I want the searching status announced politely, once per reply, so that I know something is happening without being interrupted.
25. As an Editor, I want to override the widget's searching status text, so that it matches the Agent's voice and language.
26. As an Editor, I want the Trace to list each Search in order, with its query, the Chunks it found, which were given to the model, which were excluded and why, and how long it took, so that I can debug Agentic replies.
27. As an Editor, I want Citations to work the same way in both modes, with each cited Chunk linking to the Document viewer, so that Visitors can check answers from Agentic Agents.
28. As an Editor, I want a Chunk found by two Searches in one reply shown to the model once, under one Chunk label, so that duplicate context doesn't waste tokens or confuse Citations.
29. As an Editor, I want a reply's token use and Cost to include every model call it made, so that the Cost of an Agentic reply is accurate.
30. As an Owner, I want the Token Budget to count every token an Agentic reply uses, so that the Budget caps real spend.
31. As an Editor, I want Playground use of Agentic Agents still excluded from metrics and the Token Budget but included in Organisation cost, so that testing works as it does today.
32. As an Editor, I want "searches per reply" in each Version's KPIs and in Version comparison, so that I can see how much searching an Agentic Version does.
33. As an Editor, I want the Retrieval Mode shown in the Version list and in Version Diffs, so that I can read cost and quality differences against it.
34. As an Editor, I want the fallback rate to keep its meaning in both modes, so that it's comparable across Versions in either mode.
35. As an Organisation, I want Knowledge Search to be the only tool an Agent has, and read-only, so that a successful prompt injection can still at worst produce a bad answer (ADR-0007, ADR-0015).
36. As an Organisation, I want Knowledge Search limited to the Agent's own Project, Embedding Model and Tags whatever query the model writes, so that Agentic mode can never reach a Chunk that Automatic mode couldn't.
37. As an Organisation, I want search queries checked for the Canary token, so that an injection can't leak it into a query (where it would appear in the Trace and the logs).
38. As an Organisation, I want Chunks returned by Knowledge Search spotlighted, and handled by Flagged Chunk mode, exactly as in Automatic mode, so that Agentic mode isn't a weaker path for injections.
39. As an Organisation, I want the Attack evaluation suite run against both Retrieval Modes in CI, with a Pass rate reported for each, so that Agentic mode can't quietly lower our resilience.
40. As an Editor, I want remembered turns to replay only the Visitor's and the Agent's text, not earlier searches and Chunks, so that the history stays cheap and Chunks from deleted or replaced Documents never come back.
41. As a prospective customer using the Demo Organisation, I want one Agent in each Retrieval Mode, with the Trace showing the difference, so that I can see the trade-off in the Five-minute demo.
42. As a prospective customer, I want the Demo model to work in Agentic mode without a real Provider Credential, so that the Demo Organisation still needs no key.
43. As a demo presenter, I want the Attack panel's Guardrail demo Agent to stay Automatic, so that its demonstration stays deterministic.
44. As an Editor, I want a clear error event when the provider fails partway through an Agentic reply, after a Search, so that I can tell configuration problems from retrieval problems.
45. As an Owner, I want changes to an Agent's Retrieval Mode and Search limit to show in Draft Diffs and Audit Events like any other Draft change, so that the change can be traced.

## Implementation Decisions

- **AgentConfig: Retrieval group.**
  - Add `mode` (`automatic` or `agentic`, default `agentic`) and `search_limit` (an integer from 1 to 5, default 3). `search_limit` is ignored when the mode is Automatic.
  - Only the seed script creates Agents today, so the new default needs no data migration. The seed sets each Agent's mode explicitly.
  - Both fields flow into the JSON Schema and the generated client, as other settings do, and appear in Draft Diffs and Version snapshots.
- **UI text overrides** gain `searching_status` (short text; none keeps the built-in "Searching the knowledge base…").
- **Capability registry.**
  - Each registry Model gains a `supports_tools` flag. This is a property of the model, not a new Capability: a Capability stays what a *credential* may be used for.
  - The Demo model and the Naive demo model support tools.
  - Credential and model listings expose the flag so the Studio's model picker can show it.
- **Draft validation.**
  - Saving a Draft in Agentic mode checks the *effective* chat model, meaning the Model override or else the Organisation's Default Model, and refuses one without `supports_tools`. The error names the field and the reason.
  - Changing the Default Model doesn't revalidate Drafts. At runtime an Agentic Agent whose effective model lacks tool support runs as Automatic for that reply and adds a Trace warning.
- **Retrieval module: unchanged.** Knowledge Search calls the existing `retrieve(project, query, retrieval settings)`, so isolation and every Retrieval setting apply by construction. Top-k applies per Search.
- **Agent runtime: `run_turn` keeps its signature and event-stream shape.**
  - In Automatic mode it behaves exactly as today.
  - In Agentic mode it builds the Pydantic AI agent with exactly one tool, Knowledge Search, whose only argument is `query`. It does no upfront retrieval.
  - **Streaming (ticket 13-10, a product owner decision):** each model response's text streams word by word as it arrives, exactly as in Automatic mode. A response that has already streamed text and then calls Knowledge Search was not the answer: when it ends, the runtime emits a `RetractEvent` (SSE `retract`, no data) before the Search's `search` event, and clients clear the answer text shown so far. This is a **Retraction**: it records no Guardrail outcome, and the retracted text never becomes part of the saved reply, the Trace or the Citations (its tokens are still counted, as every model call's are).
  - **Tool behaviour:**
    - The tool runs `retrieve` with the Agent's Retrieval settings.
    - It returns the new Chunks as spotlighted, labelled data blocks. Labels continue across the reply, and a Chunk already given to the model is referred to by its existing label instead of being repeated.
    - If the Search found nothing, it says plainly that nothing relevant was found.
    - Once the Search limit is reached, any further call is refused with "search limit reached; answer from what you have", and the reply is marked limit-hit.
  - **Preamble rules (Agentic only):** search before answering any question about the Knowledge Base; write complete, standalone queries, resolving follow-ups from the Conversation; greetings and small talk need no search.
  - **Fallback:**
    - If the model searched at least once and no Search returned a Chunk reaching the Minimum Score, the runtime sends the Fallback Text instead of the model's answer, with `fallback` true.
    - A reply that made no Search is not a fallback.
    - Every Search of the reply has run by the time the next model response starts streaming, so the runtime decides then: it sends the Fallback Text at once and none of the model's text. If that response turns out to search again, the Fallback Text is retracted like any other text.
  - **Canary:** each search query is checked for the Canary token before it runs. A match ends the reply as a canary leak (Fallback Text, with a Guardrail outcome), and the query isn't run. Every response's text, retracted or not, streams through the reply's Canary filter: if the canary starts to appear the stream stops and the reply is replaced (a `replace` event), as in Automatic mode. On a Retraction the text the filter held back is dropped, never released.
  - **Citations:** structured output where supported, label parsing otherwise, as today. Labels resolve against every Chunk given to the model in the reply.
  - **Usage:** input, output and cached tokens are summed across every model call in the reply. `max_output_tokens` applies to each model call.
  - **New stream event:** `SearchEvent(query, order)`, emitted as each Search starts. `DoneEvent` gains the reply's Searches, each with its query, order, latency, its candidates and excluded Chunks, and whether the limit was hit.
- **Persistence.**
  - A new **Search** record per Knowledge Search call: Message, order, query, latency and whether it was refused by the limit.
  - Message retrievals gain a nullable reference to the Search that found them (null in Automatic mode).
  - Messages gain `search_count`.
  - Message text purging (Retention Window) also purges search queries, since they can contain Visitor text.
  - Cost is computed from the summed tokens with the existing cost function. The Token Budget counter is incremented with the summed tokens.
- **Playground and widget APIs.** The SSE stream gains a `search` event carrying the query for the Playground and no query for the widget, so Visitors don't see the model's internal queries, and a `retract` event (no data) for a Retraction. The Trace endpoint returns Searches in order, with their Message retrievals nested.
- **Analytics.** Usage rollups add a search count per Agent Version per day. Version KPIs and Version comparison add mean searches per reply. The Version list and Diff show the Retrieval Mode.
- **Studio UI.**
  - **Retrieval section:** a segmented control for the Retrieval Mode with its one-sentence trade-off, and the Search limit field, shown only in Agentic mode.
  - **Model picker:** marks models that support tools.
  - **Playground:** a "Searching: …" line per Search, in reply order. A Retraction clears the answer text shown so far.
  - **Trace drawer:** a Search list with nested Chunks, plus the limit-hit and Automatic-fallback warnings.
  - All of it uses the Tidepool design system.
- **Widget.** A searching status row while Searches run, using the `searching_status` override. It's announced once per reply through the existing polite live region (the Reply announcement pattern), and replaced when the answer starts streaming. A Retraction clears the reply's text and shows the status row again; retracted text is never announced.
- **Demo provider.** In Agentic mode the Demo model and the Naive demo model make one Knowledge Search with the Visitor's question, then answer as they do today from the first Chunk the Search returned.
- **Seed.**
  - The Demo Organisation has one Agentic and one Automatic Agent over the same Project, and the Five-minute demo script points out the difference in their Traces.
  - The Attack panel's Guardrail demo Agent is explicitly Automatic.
- **Attack evaluation suite.** Each attack runs once per Retrieval Mode. The report gives a Pass rate per mode, and CI gates both.
- **Doc changes.** Spec 04's "no tools registered" and spec 08's "no tools" wording now read "no tools that act outside the Conversation; Knowledge Search is the only, read-only tool (ADR-0015)".

## Testing Decisions

- **Good tests** observe streamed events, persisted Messages, Searches and Traces through the API, as the Playground and widget do. They don't assert on prompt strings, apart from extending the one prompt-assembly contract test to cover the Agentic preamble rules and the shape of tool results.
- **No new seams.** Spec 13 uses the shared seams in [the specs README](./README.md#shared-test-seams).
- **API seam (primary).** Playground and widget Conversations driven through the HTTP API, against real Postgres and Redis, with a scripted Pydantic AI `FunctionModel` that issues Knowledge Search calls. It covers:
  - Automatic mode unchanged: the existing Playground tests pass as they are.
  - A reply with one Search, with several Searches, and with none (a greeting).
  - Turn-wide labels, with a Chunk found twice keeping its first label, and Citations resolving across Searches.
  - The Search limit: the call after the limit is refused, the reply still answers, and the Trace shows limit-hit.
  - The Fallback Text: searched and found nothing gives the Fallback Text with no answer tokens streamed first; no Search is not a fallback.
  - Tag scoping and Project isolation holding for model-written queries.
  - Summed tokens and Cost; the Token Budget incremented with the sum (widget); Playground exemption.
  - The canary in a query ends the reply as a leak, and the query isn't run.
  - A provider error after a Search ends with a typed error event.
  - The effective model without tool support: the Draft save is refused, and at runtime the reply falls back to Automatic with a Trace warning.
  - The widget `search` event carries no query.
  - Purging removes search queries.
- **AgentConfig validation:** mode and limit bounds; a model or Default Model without tool support; the JSON Schema checked by the client drift check.
- **Adapter fakes:** the default fake chat model, used by `docker compose` and end-to-end runs, and the Demo model each gain the scripted one-Search path.
- **Frontend network seam (MSW):**
  - The Retrieval Mode control and Search limit field validate, autosave and show the server's refusal.
  - The Playground renders "Searching: …" lines from streamed `search` events.
  - The Trace drawer renders Searches with nested Chunks and the warnings.
  - The widget shows and announces the searching status, and honours the override.
  - Version KPIs, comparison and Diff show searches per reply and the mode.
- **End-to-end seam:** create an Agent on the seeded Project (Agentic by default), ask a question in the Playground, see a "Searching" line, a cited answer and a Search in the Trace. The axe checks cover the widget status.
- **Attack evaluation suite:** the existing runner tests extended so each attack runs in both modes, and the report shows a Pass rate per mode.
- **Live suite:** one real Anthropic or OpenAI Agentic reply against the seed Knowledge Base that makes at least one Search and cites a Chunk.
- **Prior art:**
  - The Playground, Playground errors and retrieval integration tests.
  - The prompt-assembly contract test and the canary tests from spec 08.
  - The attack eval runner tests.
  - Spec 07's rollup and Version comparison tests.
  - The widget's Reply announcement tests.

## Out of Scope

- Any tool other than Knowledge Search, and any tool that acts outside the Conversation (ADR-0007, ADR-0015).
- The model choosing Tags, Top-k or other retrieval settings per Search.
- An upfront search in Agentic mode, or a hybrid "search first, then let the model search more" mode.
- Replaying earlier replies' Searches or Chunks in remembered turns.
- Showing search queries to Visitors.
- A per-Retrieval-Mode filter on Organisation cost (it already splits by Agent).
- Query rewriting or multi-query expansion inside Automatic mode.
- Sub-agents, planning steps or reflection loops beyond the model's own tool calls.

## Further Notes

- **Keep `run_turn` and `retrieve` small and stable.** Agentic mode should be a branch inside the runtime, not a second runtime, so specs 06–08 keep working unchanged.
- **Agentic answers stream word by word, with Retraction (ticket 13-10).** Spec 13 first held each response's text until the response ended, so text a model wrote before calling Knowledge Search was never sent. The product owner chose streaming instead: Agentic replies stream like Automatic ones, and pre-tool text that was sent is retracted with a `retract` event. Pydantic AI still runs each tool call before the next model response streams, so the Fallback decision is made as that response starts, with no answer tokens sent first.
- **Agentic replies are slower.** Each Search adds a model round trip. The searching status is what keeps that from looking like a hang, so don't drop it as polish.
- **The Knowledge Base is a confounder.** It is live and unversioned (ADR-0003), and Agentic mode makes more of it reachable per reply, so the Confounder note on Version comparison matters more when comparing across modes.
- **Tickets:** [`docs/tickets/13-agentic-retrieval/`](../tickets/README.md#13-agentic-retrieval): ten tickets, 13-01 to 13-10. 13-01 is a prefactor and 13-02 the tracer; 13-03 to 13-06 and 13-08 can start once the tracer lands, 13-07 follows 13-04, and 13-09 switches the default to Agentic. 13-10, a later product owner decision, streams Agentic answers word by word with retraction.
