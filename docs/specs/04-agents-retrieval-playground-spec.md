# Spec 04: Agents, retrieval and Playground

## Problem Statement

A Knowledge Base on its own doesn't answer anyone's questions. Editors need to turn a Project's Knowledge Base into one or more Agents with distinct purposes: a terse internal HR helper, a friendly public product FAQ. Each needs its own prompt, model, retrieval behaviour and personality. Editors also need to try an Agent safely before anyone outside sees it, and to understand *why* it answered the way it did. Without that visibility, tuning an Agent is guesswork.

## Solution

Editors create Agents inside a Project and edit each Agent's Draft across every configuration group:
- **Behaviour:** system prompt in a markdown editor, model override, temperature, max tokens, remembered turns, "I don't know" fallback text.
- **Retrieval:** top-k, hybrid weighting, minimum relevance, Tag scoping, optional reranker, citations.
- **Experience:** name, avatar, greeting, starter questions, UI text, rating prompt timing.
- **Guardrails:** settings stored now and enforced in spec 08.

Project Instructions can be edited as plain markdown for the Project, and are versioned in spec 05.

The Playground lets an Editor chat with the Draft. Answers stream in with citations. Each reply's Trace shows the model used, tokens, latency, and exactly which Chunks were retrieved with their scores and whether they were cited. Playground Conversations are recorded but flagged, so they never affect metrics.

## User Stories

1. As an Editor, I want to create an Agent in a Project with a name, so that I can start configuring it.
2. As an Editor, I want several Agents per Project, so that different audiences get different behaviour over the same Knowledge Base.
3. As an Editor, I want to see a Project's Agents with their status, so that I can manage them.
4. As an Editor, I want to edit the Agent's system prompt in a lightweight markdown editor, so that I can write structured instructions comfortably.
5. As an Editor, I want the editor to store markdown and round-trip it exactly, so that what I write is what the model receives.
6. As an Editor, I want an Agent to use the Organisation's Default Model unless I override it, so that most Agents need no model setup.
7. As an Editor, I want to override the model by choosing a chat-capable Provider Credential and one of its models, so that each Agent can trade cost against quality.
8. As an Editor, I want to set temperature and max output tokens, so that I can tune creativity and length.
9. As an Editor, I want to choose how many previous turns the Agent remembers, so that I can balance context against cost.
10. As an Editor, I want to set the text the Agent replies with when nothing relevant is found, so that it says "I don't know" in our voice instead of inventing an answer.
11. As an Editor, I want to set how many Chunks are retrieved, so that I control how much context is provided.
12. As an Editor, I want to adjust the balance between semantic and keyword matching, so that exact terms like product codes are found reliably.
13. As an Editor, I want to set a minimum relevance threshold, so that weakly related Chunks are ignored and the fallback fires instead.
14. As an Editor, I want to limit an Agent to Documents with certain Tags, so that an HR Agent only sees HR material within a shared Project.
15. As an Editor, I want to turn on a reranker using a Voyage or Bedrock credential, so that the best Chunks rise to the top when quality matters.
16. As an Editor, I want to choose whether citations are shown to Visitors, so that answers can link to their sources when appropriate.
17. As an Editor, I want to set the Agent's display name, avatar, greeting and starter questions, so that Visitors get a welcoming, guided start.
18. As an Editor, I want to override the widget's built-in text ("Send", "Rate this conversation", the unavailable message), so that the Agent speaks our language and tone.
19. As an Editor, I want to choose after how many replies Visitors are asked to rate the Conversation, so that the prompt is well timed for this Agent.
20. As an Editor, I want to set the input Guardrail mode (block, warn or log) and an optional LLM classifier, so that protections fit the Agent's risk.
21. As an Editor, I want form validation explaining invalid settings (for example, a model the credential doesn't support), so that I can't save a broken configuration.
22. As an Editor, I want the Draft saved automatically and to see that it has changes not yet published, so that I never lose work.
23. As an Editor, I want to edit Project Instructions as markdown that applies to every Agent in the Project, so that shared rules live in one place.
24. As an Editor, I want to chat with the Agent's Draft in a Playground, so that I can test changes before anyone else sees them.
25. As an Editor, I want answers in the Playground to stream in token by token, so that it feels like the real experience.
26. As an Editor, I want citations in the Playground linking to the Document and Chunk, so that I can check an answer against its source.
27. As an Editor, I want to open the Trace for any reply, so that I can see the model, tokens, cost, latency, retrieved Chunks with scores, which were cited, and Guardrail outcomes.
28. As an Editor, I want to see Chunks that were retrieved but filtered out by the threshold or Tags, so that I can tune retrieval with evidence.
29. As an Editor, I want to reset the Playground Conversation, so that I can test from a clean slate.
30. As an Editor, I want to change the Draft and immediately re-ask in the Playground, so that iterating is fast.
31. As an Editor, I want Playground Conversations excluded from metrics and from the Token Budget, so that testing doesn't distort analytics or take the Agent offline.
32. As an Editor, I want Playground usage to still count towards cost reporting, so that the Organisation sees what testing costs.
33. As an Editor, I want a clear error in the Playground when the provider fails (invalid key, rate limited, model unavailable), so that I can fix configuration problems.
34. As an Editor, I want to Archive an Agent, so that it's retired without losing its history.
35. As an Owner, I want to permanently delete an archived Agent after typing its name, so that it's truly gone when required.
36. As an Owner, I want Agent create, archive, restore and delete, and Project Instructions edits, recorded as Audit Events, so that changes are traceable.
37. As an Editor, I want the Agent's model, reranker and classifier credentials registered as references, so that a credential can't be deleted out from under the Agent.

## Implementation Decisions

- **AgentConfig.** One Pydantic model (stored as `jsonb`, validated on read and write) with nested groups:
  - Behaviour: system prompt, model override (credential plus model, or none to follow the Default Model), temperature, max output tokens, remembered turns, fallback text.
  - Retrieval: top-k, hybrid weighting, minimum score, Tag IDs, reranker (credential plus model, or none), citations on or off.
  - Experience: display name, avatar, greeting, starter questions, UI text overrides, rating prompt reply count.
  - Guardrails: input mode, LLM classifier (credential plus model, or none).

  Its JSON Schema is exposed through OpenAPI so the Studio form is typed. Operational Settings and Theme overrides are **not** part of it (ADR-0009).
- **Agents module.** An Agent has a public ID (unguessable, used by the embed in spec 06), a Project, an `archived_at`, and one Draft holding an AgentConfig. Version fields arrive in spec 05. Saving the Draft validates the model against the credential capability registry from spec 02 and registers credential references.
- **Project Instructions in this slice:** a single markdown Draft per Project. Spec 05 adds Versions and the Current Version without changing how the runtime reads it: the runtime always receives "the Instructions text to use" from its caller.
- **Retrieval module.** A deep module with one main operation, `retrieve(project, query, retrieval settings) → ranked candidates with scores, plus excluded candidates with reasons`.
  1. Embed the query with the Project's active Embedding Model.
  2. Run pgvector cosine search and Postgres full-text search, each limited to the Project, the active model and the Agent's Tags.
  3. Fuse with weighted reciprocal rank fusion, using the hybrid weighting.
  4. Optionally rerank through the model gateway.
  5. Apply the minimum score and top-k.
  Excluded candidates and their reasons feed the Trace.
- **Agent runtime module.** One operation: `run_turn(conversation context, AgentConfig, Instructions text, Visitor input) → async stream of events (token, citation, final usage and Trace)`. It:
  - assembles the prompt in a fixed order: platform preamble (spotlighting rules; the canary placeholder is wired here and enforced in spec 08), Project Instructions, the Agent system prompt, remembered turns, then retrieved Chunks and Visitor input in labelled, delimited data blocks;
  - calls the model through a Pydantic AI agent built by the model gateway, with no tools registered (ADR-0007);
  - uses the fallback text when retrieval returns nothing above the threshold;
  - works out citations by asking the model to reference Chunk labels and resolving them back to Chunk IDs.
  The runtime knows nothing about HTTP, Playground or widget; spec 06 reuses it unchanged.
- **Conversation and Message persistence**, introduced here and extended in spec 07:
  - Conversation: Agent, is-Playground flag, last activity.
  - Message: role, content, model provider and name, token counts, latency fields, and the Draft-or-Version marker (Playground replies are tagged "Draft"; spec 05 adds Version references).
  - Message retrievals: Chunk ID, score, rank, cited flag, excluded reason.
  - Cost is calculated with spec 02's pure function and stored on the Message.
- **Playground API.** Create a Playground Conversation for an Agent, then send a message, which returns a Server-Sent Events stream of token, citation and done events (the done event includes the Message ID). Get the Trace for a Message. Editor or Owner only.
- **Token Budget** isn't enforced here (spec 06). The Playground is explicitly exempt.
- **Studio UI.** Agent list on the Project page. Agent editor with grouped sections, the TipTap markdown editor component from the shared UI package, Draft autosave indicator. Playground panel beside the editor, with streaming messages, citation chips and a Trace drawer. Project Instructions editor on the Project page.

## Testing Decisions

- **Good tests** observe streamed events, persisted Messages and Traces through the API, as the Playground would. They don't assert on intermediate prompt strings except for one deliberate prompt-assembly contract test (below).
- **API seam** with the Pydantic AI `FunctionModel` fake. The fake can:
  - echo what it was given (to prove Instructions, system prompt, Chunks and history reach the model in the right blocks and order: the prompt-assembly contract test);
  - stream fixed tokens;
  - cite given Chunk labels;
  - raise provider errors of each type.
- **Retrieval** is tested through its interface against real Postgres with pgvector and the deterministic embedder, on a fixture Knowledge Base with known relevant and irrelevant Chunks. It covers: semantic hits, exact-keyword hits only full-text search finds, the effect of hybrid weighting, Tag scoping, the threshold triggering the fallback, the reranker reordering (fake reranker), and Project and Embedding Model isolation.
- **AgentConfig validation:** credential capability mismatch, an unknown Tag, out-of-range values. JSON Schema export is checked by the client drift check.
- **Edge cases:** Playground Conversations flagged and excluded from the metrics queries from spec 07 (a placeholder assertion is added here and grows later); remembered turns are truncated correctly; provider errors become a typed error event in the stream; Archive blocks new Playground Conversations.
- **Frontend, network seam:** the editor validates and autosaves; the markdown editor round-trips headings, lists, code and links exactly (a table of markdown fixtures); the Playground renders a streamed reply (MSW streaming handler), citations and the Trace drawer contents; error events show the right message.
- **End-to-end:** create an Agent on the seeded Project, ask a question in the Playground, a streamed answer arrives with a citation, open the Trace.
- **Live suite:** a real Anthropic or OpenAI call and a real local-model embedding against the seed Knowledge Base.
- **Prior art:** spec 03's ingestion fixtures and retrieval probe, spec 02's model gateway fakes and cost function.

## Out of Scope

- Publishing, Versions, the Live Version, Project Instructions Versions and bulk actions (spec 05).
- Serving to Visitors, Operational Settings and enforcing the Token Budget (spec 06).
- Feedback, ratings and analytics (spec 07).
- Enforcing Guardrails beyond prompt structure (spec 08). The settings are stored and passed through.
- Tools of any kind for Agents (ADR-0007).

## Further Notes

- The runtime and retrieval modules are the heart of the product. Keep their interfaces small and stable, because specs 05–08 build around them without changing their shape.
- Ask the model for citations through structured output (Pydantic AI result types) where the provider supports it, falling back to parsing labels.
