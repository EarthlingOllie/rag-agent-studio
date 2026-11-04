# Layered prompt-injection defence, with no side-effecting tools

Agents never get tools that change anything outside the conversation, so a successful injection can at worst produce a bad answer. On top of that limit we layer: spotlighting (Visitor input and retrieved Chunks wrapped as labelled, untrusted data), an input Guardrail classifier configurable per Agent (block, warn or log), a canary token whose appearance in output blocks the response, ingestion-time scanning that flags instruction-like Chunks, and an attack-prompt evaluation suite run in CI. Every block is logged against its Message with a reason.

The input Guardrail defaults to a platform-run local classifier (a small ONNX prompt-injection model, alongside the local embeddings). It needs no credentials, costs nothing per message and is deterministic in tests. An Agent can additionally enable an LLM classifier that uses its own Provider Credential.
