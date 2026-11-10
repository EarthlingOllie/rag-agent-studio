---
status: proposed
---

# Agentic Retrieval Mode gives the model one read-only tool, Knowledge Search

An Agent's Retrieval Mode is either Automatic (one Hybrid search on the Visitor input, then one model call: the behaviour specs 04–08 were written against) or Agentic, where the model is given Knowledge Search and decides whether, how often and with what query to search. Agentic answers multi-part, vague and follow-up questions better, at the cost of more model calls and tokens. The mode is part of AgentConfig, so it is versioned (ADR-0003). That lets Version comparison measure the accuracy against cost trade-off directly, and it keeps the mode out of Operational Settings (ADR-0009).

This narrows the earlier "Agents have no tools" wording in specs 04 and 08 to what ADR-0007 actually relies on: **no tool that acts outside the Conversation**. Knowledge Search is the only tool, and it is read-only:
- The model supplies only the query. Project, Embedding Model, Tag scoping, Minimum Score, Reranker and Top-k all come from the Agent's Retrieval settings, so Agentic mode can never reach a Chunk that Automatic mode couldn't.
- Its results get the same spotlighting as pre-retrieved Chunks.

A successful injection can still at worst produce a bad answer, or a few wasted searches.

In Agentic mode there is no upfront search. The model may answer a greeting or a follow-up without searching, so Agentic is not always the more expensive mode.

## Considered options

- **Always run the Automatic search, then let the model search more.** This would always cost at least as much as Automatic, and it blurs the line between the two modes.
- **Let the model also choose Tags or Top-k.** This gives an injected Chunk more to steer and would make isolation depend on validating what the model sent. It was rejected for v1.
- **Build Agentic mode as a runtime loop rather than a tool,** to keep the "no tools" wording. That would hide the real change in the prompt-injection surface instead of recording it.
