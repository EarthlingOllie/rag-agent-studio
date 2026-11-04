# Spec 08: Guardrails and evaluation

## Problem Statement

A public, anonymous chat box connected to an Organisation's documents and model credentials is an obvious target:
- **Direct attacks:** Visitors try to make the Agent ignore its instructions, reveal its system prompt, adopt a different persona, or produce content that embarrasses the brand.
- **Indirect attacks:** an uploaded Document can contain hidden text addressed to the model.

Organisations need layered protection that works without extra setup, that they can tune per Agent, that tells them when and why something was blocked, and that can be shown to work rather than merely claimed.

## Solution

Several Guardrail layers sit around the Agent runtime, on top of the structural guarantee that Agents have no tools that act outside the conversation (ADR-0007):
- **Spotlighting** (spec 04) marks Visitor input and retrieved Chunks as untrusted data.
- **Input Guardrail:** a local prompt-injection classifier runs on every Visitor message by default, and an optional LLM classifier can be added using the Agent's own Provider Credential. Each Agent chooses block, warn or log.
- **Canary token:** a random value placed in every prompt. If it appears in output, the reply is stopped mid-stream and replaced.
- **Ingestion scan:** upgraded from the heuristic baseline (spec 03) to the local classifier.

Every Guardrail outcome is recorded in the Trace and counted in analytics. An attack evaluation suite, a versioned set of attack prompts with expected outcomes, runs in CI against the mocked model and nightly against a real one.

## User Stories

1. As an Organisation, I want every Agent to have no tools that act outside the conversation, so that a successful attack can at worst produce a bad answer, never an action.
2. As an Editor, I want Visitor input and retrieved Chunks always presented to the model as clearly marked untrusted data, so that instructions hidden in them are less likely to be followed.
3. As an Editor, I want every Visitor message checked by an injection classifier by default with no setup, so that protection works the moment an Agent is live.
4. As an Editor, I want to choose block, warn or log for the input Guardrail per Agent, so that I can balance safety against false positives.
5. As an Editor, I want "block" to stop the message before it reaches the model and reply with a configurable refusal, so that attacks don't cost tokens or produce output.
6. As an Editor, I want "warn" to let the message through but add an extra caution to the prompt and flag it, so that borderline messages are handled carefully.
7. As an Editor, I want "log" to only record the classifier's verdict, so that I can measure false positives before enforcing.
8. As an Editor, I want to turn on an additional LLM classifier using our own Provider Credential and a cheap model, so that high-risk Agents get a stronger check.
9. As an Editor, I want the LLM classifier to fail open or fail closed according to my choice when the provider errors, so that an outage behaves the way we decided.
10. As an Editor, I want to set the refusal text Visitors see when a message is blocked, so that refusals are polite and on-brand.
11. As an Editor, I want a canary token in every prompt and the reply stopped if the canary appears, so that system-prompt leaks are caught even when the classifier misses them.
12. As a Visitor, I want a leaked reply cut off cleanly and replaced with the fallback text, so that I never see half a leaked prompt.
13. As an Editor, I want Chunks that contain instructions aimed at an AI flagged at upload by the same classifier, so that poisoned Documents are spotted.
14. As an Editor, I want to choose per Project whether flagged Chunks are excluded from retrieval or only marked, so that I can quarantine suspicious content.
15. As an Editor, I want to clear a false-positive flag on a Chunk, recorded as an Audit Event, so that legitimate content isn't excluded forever.
16. As an Editor, I want every Guardrail outcome (layer, verdict, score, reason, action taken) shown in the Trace, so that I know which layer stopped what.
17. As an Editor, I want Guardrail block rates per Version in analytics, so that I can see whether a change made the Agent more or less exposed.
18. As an Editor, I want to filter Conversations to those with Guardrail events, so that I can review attacks.
19. As an Owner, I want an alert badge when an Agent's block rate spikes, so that I notice an active attack.
20. As a developer, I want a versioned attack evaluation suite covering instruction override, system-prompt extraction, role-play jailbreaks, indirect injection through Documents, encoding tricks (base64, homoglyphs, translation) and multi-turn escalation, so that defences are measured, not assumed.
21. As a developer, I want each attack case to declare the expected outcome per layer (blocked by input, caught by canary, harmless answer), so that regressions are precise.
22. As a developer, I want the suite to run in CI on every PR against the mocked model, so that changes to the prompt assembly or Guardrails can't silently weaken defences.
23. As a developer, I want the suite to run nightly against a real model with a pass-rate report, so that we track real-world resilience over time.
24. As a developer, I want benign cases in the suite too, so that false positives are measured alongside detections.
25. As an interviewer, I want an attack panel page that fires sample attacks at a demo Agent and shows which layer stopped each one, so that I can see the defences working.

## Implementation Decisions

- **Guardrail pipeline module.** It wraps the runtime from spec 04 without changing its interface. Pre-model:
  1. The input classifiers (local, then LLM if enabled) produce verdicts.
  2. The mode decides the result: block (short-circuit with the refusal event), warn (add a caution block to the prompt), or log.

  In-stream:
  - The canary filter wraps the token stream. It holds back a trailing buffer as long as the canary and releases text only once it's certain the canary isn't straddling chunk boundaries.
  - On detection it stops the model stream, emits a replace event carrying the fallback text, and records the outcome.

  Outcomes accumulate into the Message's Guardrail outcomes field (spec 07).
- **Injection classifier port** (spec 03 introduced it).
  - Local adapter: a small ONNX prompt-injection model (a DeBERTa-v3-based prompt-injection classifier) run with onnxruntime on CPU, loaded once per process. Inputs over the model's length are split into windows, and the highest score is used. The threshold is configurable.
  - LLM adapter: a structured-output Pydantic AI call through the model gateway with a fixed classifier prompt, returning label, score and reason.
  - Fake adapter: rule-driven, for deterministic tests.
- **Canary.** A per-request random token placed in the platform preamble with an instruction never to reveal it. The comparison normalises whitespace and case. Base64-encoded or spaced-out canaries are matched in a post-completion check that logs and flags, but can't un-send what has already streamed. This limitation is documented.
- **Ingestion scan upgrade.** The ingestion pipeline (spec 03) uses the local adapter. A per-Project setting chooses "mark" or "exclude" for flagged Chunks, and retrieval (spec 04) honours "exclude". Clearing a flag is an Editor action and is audited.
- **AgentConfig fields** (already present from spec 04): input mode, LLM classifier credential and model, fail-open/closed, refusal text. They're versioned with the Agent.
- **Spike alert.** The hourly rollup (spec 07) compares the block rate against a baseline and sets an alert flag on the Agent above a threshold. It uses the same badge mechanism as spec 06.
- **Evaluation suite.**
  - Format: a data file in the repo, versioned with a schema. Each case has an ID, category, turns (multi-turn allowed), optional poisoned Document content, the expected outcome per layer, and whether it's benign.
  - A runner executes the cases through the real Guardrail pipeline and runtime, using either a mocked model (a `FunctionModel` that simulates a naive model that *would* comply with injected instructions, so the Guardrails are tested rather than the model's own refusals) or a real model in the live job.
  - The output is a per-category report (JSON plus a markdown summary). The CI job fails on any unexpected outcome in mocked mode. The nightly job publishes the report as an artifact and fails below a configured pass rate.
- **Attack panel.** A seed page (spec 10) calling the widget API for a demo Agent with buttons for categories of attack, showing the stream and the Trace outcome. It uses a Playground-like debug endpoint available only in demo/seed mode, so it returns Traces without a Studio login.

## Testing Decisions

- **Good tests** send messages through the widget or Playground API and assert what the Visitor receives (refusal, cut-off and replacement, normal answer) and what the Trace records. They don't assert classifier internals.
- **API seam:**
  - block, warn and log modes with the rule-driven fake classifier;
  - the LLM classifier enabled, including fail-open and fail-closed on provider error;
  - refusal text;
  - the canary appearing mid-stream (the `FunctionModel` streams the canary split across several chunks) gives a clean replacement with no canary fragment in any emitted event;
  - the canary in the post-completion check;
  - Guardrail outcomes in the Trace; block rate in analytics after a rollup;
  - the spike alert flag.
- **Canary stream filter:** tested through its interface with table-driven chunkings, covering the canary at the start, middle and end, split at every position, and near misses.
- **Local classifier adapter:** a live-suite test with the real ONNX model against a small labelled set. A unit test with a stubbed session checks the windowing and maximum-score logic.
- **Ingestion:** with the "exclude" setting, a flagged Chunk never appears in retrieval candidates; clearing a flag restores it and is audited.
- **Evaluation suite:** runs as its own CI job (mocked), and the runner itself is covered by unit tests on a tiny case file. Live nightly against a real provider.
- **Frontend, network seam:** Trace drawer rendering of Guardrail outcomes, the Conversations filter, the Agent Guardrail settings form, Chunk flag clearing, the widget's refusal and replacement rendering.
- **End-to-end:** on the attack panel, an override attack is blocked by input, a leak attempt is caught by the canary (forced with the mocked model), and a benign question is answered.
- **Prior art:** spec 04 runtime fakes, spec 07 analytics tests, spec 03 ingestion scan hook.

## Out of Scope

- Output moderation for toxicity or brand safety beyond the canary (possible future layer).
- Training or fine-tuning a custom classifier.
- PII detection and redaction in Visitor input.
- Tools for Agents, and therefore tool-use defences (ADR-0007).

## Further Notes

- The honest framing for interviews: no layer is perfect. The design limits the blast radius (no tools), adds independent detection layers, and *measures* resilience with the evaluation suite.
- Keep the mocked "naive model" in the eval runner. If the mock refused attacks by itself, the suite would only test the mock.
