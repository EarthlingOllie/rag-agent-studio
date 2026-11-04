# 01: Agent and Playground tracer

**Ticket:** `04-01` · **Spec:** [Agents, retrieval and Playground](../../specs/04-agents-retrieval-playground-spec.md)

**What to build:** An Editor creates an Agent in a Project, writes a system prompt, and chats with its Draft in the Playground, getting a streamed answer grounded in Chunks retrieved from the Project's Knowledge Base.

**Blocked by:**
- [03-02: Upload a Document to Ready](../03-projects-knowledge-base/02-upload-document-to-ready.md)
- [02-03: Model gateway and Default Model](../02-provider-credentials-theme/03-model-gateway-default-model.md)

**Status:** ready-for-agent

- [ ] The AgentConfig Pydantic model starts with system prompt and top-k, is stored on the Agent's Draft, and the Agent gets a public ID
- [ ] The retrieval module runs vector search limited to the Project and its active Embedding Model
- [ ] The Agent runtime assembles the prompt in a fixed order with spotlighting blocks, registers no tools, and uses the Default Model through the gateway
- [ ] Conversations (with a Playground flag) and Messages (with tokens and latency) are saved
- [ ] The Playground SSE endpoint streams token and done events, and the Playground UI renders them
- [ ] A prompt-assembly contract test uses an echoing `FunctionModel`
- [ ] End-to-end: create an Agent → ask a question → receive a streamed answer
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
