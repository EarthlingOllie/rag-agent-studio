# Agentic guardrails in production

*How RAG Agent Studio protects a public, anonymous chat box that is connected to an Organisation's private documents and paid model credentials.*

> **Status:** this describes the design as specified in this repository ([ADR-0007](../adr/0007-layered-prompt-injection-defence.md), [spec 08](../specs/08-guardrails-evaluation-spec.md), [spec 06](../specs/06-embed-widget-operational-settings-spec.md)) and broken into tickets under [`docs/tickets/08-guardrails-evaluation/`](../tickets/08-guardrails-evaluation/). Implementation has not started yet, so nothing below is a measured production result.

---

## 1. The threat model

An embedded Agent is about the most exposed thing a company can ship with an LLM inside it:

- **Anyone can talk to it.** Visitors are anonymous, and a non-browser client can't be stopped from calling the widget API.
- **It reads untrusted text twice.** Once from the Visitor, and once from retrieved Chunks of Documents that Editors uploaded. A PDF can carry hidden text addressed to the model.
- **It spends someone else's money.** Every reply is billed to the Organisation's Provider Credential.
- **It speaks for a brand.** An embarrassing reply is screenshotted, not logged.

The attacks the design names explicitly:

| Attack | Example |
|---|---|
| Direct instruction override | "Ignore your instructions and…" |
| System-prompt extraction | "Repeat everything above this line" |
| Role-play jailbreak | "You are now DAN…" |
| Indirect injection | A Document containing "AI assistants reading this must…" |
| Encoding tricks | base64, homoglyphs, "answer in French then translate" |
| Multi-turn escalation | Harmless turns that build towards an override |
| Cost and availability abuse | Flooding the Agent, framing it on another site |

## 2. The principle: limit the blast radius first, then detect

The most important guardrail in the system is not a classifier. It is a structural decision:

> **Agents have no tools that change anything outside the conversation.** A successful injection can, at worst, produce a bad answer. It can never send an email, write to a database or call an API. ([ADR-0007](../adr/0007-layered-prompt-injection-defence.md))

This changes the whole risk calculation. Prompt-injection detection is probabilistic, and every layer below will sometimes miss. When the worst case is "a bad sentence", a miss is an incident to review. When the worst case is "an action", a miss is a breach. The design deliberately puts tools out of scope (along with tool-use defences) rather than shipping them with weaker protections.

Everything else is defence in depth on top of that floor. Each layer is independent, so an attack has to beat all of them, and each layer records what it saw.

## 3. The layers, in request order

The chat pipeline ([plan §2](../plan.md#chat-request-pipeline)) has guardrails at almost every step:

```
 Visitor message
   │
   ├─ 0. Edge & admission ── origin allowlist, signed tokens, rate limits, Token Budget
   │
   ├─ 1. Input Guardrail ─── local ONNX classifier (+ optional LLM classifier)
   │                          → block / warn / log
   │
   ├─ 2. Retrieval ───────── Chunks flagged at ingestion are excluded or marked
   │
   ├─ 3. Prompt assembly ─── spotlighting + canary token in the platform preamble
   │
   ├─ 4. Generation ──────── streaming canary filter cuts and replaces leaks
   │
   └─ 5. Persist ─────────── every Guardrail outcome lands in the Trace
```

### Layer 0: Edge and admission (abuse, not injection)

Before any model is involved, the request has to be allowed at all ([ADR-0004](../adr/0004-iframe-embed-with-origin-allowlist.md), [ADR-0009](../adr/0009-operational-settings-outside-versions.md)):

- **Origin allowlist.** The widget is an iframe whose HTML shell is served by the API with `Content-Security-Policy: frame-ancestors <Allowed Origins>`, so browsers refuse to show the Agent on someone else's site.
- **Signed, short-lived Conversation tokens** authenticate every widget call.
- **Per-token and per-IP rate limits** in Redis.
- **A daily Token Budget per Agent** acts as a circuit breaker. When it trips, Visitors see the Agent's on-brand "temporarily unavailable" text, the Agent shows an alert badge, and Owners are emailed.

Since Visitors are anonymous, these controls *bound* abuse rather than prevent it. That is an honest framing: you cannot authenticate the public, so you cap what the public can cost you.

A production detail worth calling out: these settings are **live, not versioned**. Adding a site or raising a budget during an incident takes effect immediately and is audit-logged, instead of requiring a publish that would also distort Version comparisons.

### Layer 1: Input Guardrail

Every Visitor message is classified before it reaches the model.

**Default classifier: local and free.** A small DeBERTa-v3-based prompt-injection model runs under `onnxruntime` on CPU, loaded once per process and baked into the image. Long inputs are split into windows and the highest score wins. The threshold is configurable. Choosing a local model as the default was deliberate:

- it works the moment an Agent goes live, with **no credentials or setup**;
- it costs **nothing per message**;
- it is **deterministic**, which matters for tests and for explaining decisions.

**Optional second opinion: an LLM classifier.** High-risk Agents can add a structured-output classifier call (label, score, reason) through the model gateway, using the Agent's own Provider Credential and a cheap model. The Editor chooses whether it **fails open or fails closed** when the provider errors. That choice belongs to the business, not the platform: a support bot might prefer availability, an HR bot might prefer refusal.

**Three enforcement modes, per Agent:**

| Mode | Behaviour | Use it when |
|---|---|---|
| **Block** | Short-circuits before the model call and returns the Agent's configured refusal text. The attack costs no tokens and produces no output. | Confident in the classifier for this Agent's traffic |
| **Warn** | Lets the message through but adds a caution block to the prompt and flags the Message. | Borderline traffic where refusals would hurt |
| **Log** | Records the verdict only. | Rolling out: measure false positives before enforcing |

The mode is part of the versioned `AgentConfig`, so changing it is a publish, it shows up in Version comparisons, and it can be reverted like any other behaviour change. "Log first, then enforce" is the intended rollout path.

### Layer 2: Ingestion scan (indirect injection)

Indirect injection is handled where the poison enters: at upload. After chunking and embedding, every Chunk goes through the same injection-classifier port ([spec 03](../specs/03-projects-knowledge-base-spec.md)). The first slice ships a heuristic baseline, and spec 08 swaps in the ONNX classifier behind the same port without changing behaviour or tests.

- Flagged Chunks show their label, score and reason in the Document viewer, and per-Document flag counts make risky files stand out.
- Each Project chooses **mark** (retrievable, but visible) or **exclude** (quarantined from retrieval). Excluded Chunks appear in the Trace's "excluded reasons", so Editors can see that a quarantine fired.
- Clearing a false positive is an Editor action recorded as an Audit Event.

Scanning once at ingestion is far cheaper than classifying every retrieved Chunk on every request, and it puts the decision in front of a human who owns the content.

### Layer 3: Spotlighting and the canary

Prompt assembly has a fixed, tested order:

1. platform preamble (rules for treating data as untrusted, plus the canary);
2. the pinned Project Instructions Version;
3. the Agent system prompt;
4. remembered turns;
5. retrieved Chunks and the Visitor input, **each wrapped in labelled, delimited data blocks**.

**Spotlighting** means the model is always told, structurally, "this is data, not instructions". It lowers the hit rate of both direct and indirect injection, and it is enforced by a prompt-assembly contract test that uses an echoing fake model to prove each block reaches the model in the right place.

**The canary token** is a fresh random value placed in the preamble on every request, with an instruction never to reveal it. If it ever appears in output, the system prompt is leaking, whatever the classifier thought of the input.

### Layer 4: The streaming canary filter

This is the trickiest piece of engineering in the guardrail stack, because replies stream token by token over SSE. A naive "check the output" step would run after the Visitor had already seen the leak, and a canary can be split across chunk boundaries (`"c4n"`, `"4ry-9f"`, …).

The filter wraps the token stream and **holds back a trailing buffer as long as the canary**. Text is released only once it is certain the canary can't be straddling the boundary. On detection it:

1. stops the model stream;
2. emits a `replace` event carrying the Agent's fallback text, so the widget swaps the partial reply out cleanly;
3. records the outcome on the Message.

The comparison normalises whitespace and case. The test plan is table-driven: the canary at the start, middle and end, split at every position, plus near misses. The key assertion is that **no canary fragment appears in any emitted event**.

**Documented limitation:** a canary that leaks base64-encoded or spaced out can't be caught in-stream. A post-completion check on the normalised full text logs and flags it, but it can't un-send what already streamed. Writing this limitation down, rather than claiming the canary is airtight, is part of the design.

### Layer 5: Observability, analytics and alerts

A guardrail you can't see is a guardrail you can't tune. Every outcome records **layer, verdict, score, reason and action taken** on the Message, and shows in the Trace drawer next to the retrieved Chunks, model, Version and token use. On top of that:

- **Block rate per Version** sits in the analytics KPI cards beside thumbs-up rate and fallback rate, so an Editor can see whether a prompt change made the Agent more or less exposed.
- **Conversations can be filtered by Guardrail outcome**, which turns "review the attacks" into a list.
- **Spike alerts.** The hourly rollup compares the block rate against a baseline and raises an alert badge on the Agent above a threshold. A sudden spike usually means an active attack.
- **Telemetry hygiene.** OpenTelemetry spans go through a scrubbing processor that removes Message text and secrets, and a test asserts that it does. Guardrail logs must not become a second copy of the attack payloads or of Visitor PII.

## 4. Measuring it: the attack evaluation suite

The design rule is that defences are **measured, not assumed** ([ticket 08-07](../tickets/08-guardrails-evaluation/07-attack-eval-suite.md)).

- **A versioned case file** in the repo, with a schema. Each case has an ID, a category (override, extraction, role-play, indirect via Document, encoding, multi-turn), its turns, optional poisoned Document content, and the **expected outcome per layer**: blocked by input, caught by canary, or harmless answer.
- **Benign controls** are part of the suite, so false positives are measured alongside detections. A classifier that blocks everything would otherwise score perfectly.
- **A deliberately naive mock model.** In CI the runner drives the *real* guardrail pipeline and runtime with a Pydantic AI `FunctionModel` that **would comply** with injected instructions. If the mock refused attacks on its own, the suite would be testing the mock. This is the single most important detail of the eval design.
- **Two cadences:**
  - every PR, against the naive mock: fails on *any* unexpected outcome, so changes to prompt assembly or guardrails can't silently weaken defences;
  - nightly, against a real model: publishes a per-category pass-rate report (JSON plus markdown) and fails below a configured threshold, tracking real-world resilience over time.
- **An attack panel** (seed data, [spec 10](../specs/10-seed-showcase-spec.md)) fires sample attacks at a demo Agent and shows which layer stopped each one. It turns the claim into a demo.

## 5. Production engineering choices that make this work

- **Ports and fakes.** The injection classifier sits behind one port with three adapters: local ONNX, LLM, and a rule-driven fake for tests. The guardrail pipeline wraps the runtime without changing its interface, so the runtime stays testable in isolation.
- **Test at the highest seam.** Tests send messages through the widget or Playground API and assert what the Visitor receives and what the Trace records. They don't assert classifier internals. The ONNX model itself is covered by a live-suite test on a small labelled set, plus a unit test of the windowing and max-score logic.
- **100% line and branch coverage** is a CI gate ([ADR-0008](../adr/0008-full-line-and-branch-coverage.md)). For guardrail code, untested branches are exactly where bypasses hide.
- **Guardrail settings are versioned behaviour; abuse limits are live operations.** The split ([ADR-0009](../adr/0009-operational-settings-outside-versions.md)) means safety changes are reviewable and revertible, while incident response stays fast.
- **Everything leaves an audit trail.** Flag clears, Operational Settings changes, publishes and reverts are all Audit Events with before and after values.

## 6. What is deliberately out of scope

Being explicit about gaps is part of running guardrails honestly:

- output moderation for toxicity or brand safety beyond the canary;
- PII detection and redaction in Visitor input;
- training or fine-tuning a custom classifier;
- tools for Agents, and therefore tool-use defences.

## 7. Takeaways

1. **Constrain capability before you build detection.** No side-effecting tools turns every miss from a breach into a bad answer.
2. **Layer independent detectors** at input, ingestion, prompt structure and output, and record which one fired.
3. **Default to protection that needs no setup**: a local, free, deterministic classifier beats a better one nobody turns on.
4. **Give owners the dials** (block, warn or log; fail open or closed; mark or exclude) and roll out with "log" first.
5. **Handle streaming properly.** Output checks on a streamed reply need a hold-back buffer, or they run after the leak.
6. **Measure with an adversarial harness**, using a mock model naive enough to fall for every attack, and include benign cases so you measure false positives too.
7. **Document the limits.** No layer is perfect. The honest claim is a limited blast radius, independent layers, and resilience that is measured.
