# Demo videos: the core user stories

Each video below is a screen recording of one core user story, run end to end against the seeded stack (`make dev`, then `make seed-reset`). The Studio is answered by the labelled demo model, so no provider key was used and every cost shows as $0.00. Captions at the bottom of the screen narrate each step, and an amber outline marks each control just before it is used.

Select a poster to play its video. The [five-minute demo](../README.md#five-minute-demo) in the README walks the same ground by hand.

| # | Story | Who | Length |
| --- | --- | --- | --- |
| 1 | [Sign up and create a Project](#1-sign-up-and-create-a-project) | New Owner | 0:29 |
| 2 | [Build a Knowledge Base](#2-build-a-knowledge-base) | Owner or Editor | 0:32 |
| 3 | [Create an Agent and test it in the Playground](#3-create-an-agent-and-test-it-in-the-playground) | Editor | 0:36 |
| 4 | [Publish an Agent and embed it on a website](#4-publish-an-agent-and-embed-it-on-a-website) | Editor, then a Visitor | 0:42 |
| 5 | [Iterate safely with Versions, Diffs and revert](#5-iterate-safely-with-versions-diffs-and-revert) | Editor | 0:32 |
| 6 | [Review Conversations and compare Versions](#6-review-conversations-and-compare-versions) | Editor | 0:36 |
| 7 | [Choose Automatic or Agentic retrieval](#7-choose-automatic-or-agentic-retrieval) | Editor, then a Visitor | 0:49 |
| 8 | [See the Guardrails stop prompt injection](#8-see-the-guardrails-stop-prompt-injection) | Organisation | 0:37 |
| 9 | [Manage the team, spending and audit trail](#9-manage-the-team-spending-and-audit-trail) | Owner | 0:49 |

## 1. Sign up and create a Project

> As a team lead new to RAG Agent Studio, I want to sign up, get my own Organisation and create a first Project, so that I have somewhere to build an assistant for my team.

[![Sign up and create a Project](demo/01-get-started.jpg)](demo/01-get-started.mp4)

- Sign up with a name, email, password and Organisation name. The new Member is the Organisation's Owner.
- **New Project** opens a dialog. The new Project opens on its empty Documents section.
- Organisation settings hold the provider Credentials, Models, Theme, Members and Audit log.

## 2. Build a Knowledge Base

> As a Member, I want to upload my team's documents and see exactly how they were read, so that I can trust what an Agent will answer from.

[![Build a Knowledge Base](demo/02-knowledge-base.jpg)](demo/02-knowledge-base.mp4)

- Upload four files at once: two Markdown files, a DOCX and a PPTX.
- Each one goes from Queued to Processing to Ready while it is converted to Markdown, split into Chunks and embedded with the local Embedding Model.
- The Document viewer shows the converted Markdown beside its Chunks.
- The planted "note for AI assistants" in the returns policy is flagged at ingestion: the first defence against indirect prompt injection.

## 3. Create an Agent and test it in the Playground

> As an Editor, I want to create an Agent, tell it how to behave and which Documents to use, and try it before anyone else can, so that I only publish something I've seen work.

[![Create an Agent and test it in the Playground](demo/03-build-an-agent.jpg)](demo/03-build-an-agent.mp4)

- **New Agent** creates a Draft. The configuration autosaves.
- Write the system prompt and scope retrieval to the Products Tag.
- Ask the Playground a question. The answer streams in with Source chips that link to the cited Chunk.
- The Trace shows the model, tokens, cost, latency and every Chunk retrieved, given to the model or excluded.

## 4. Publish an Agent and embed it on a website

> As an Editor, I want to publish my Agent and put it on our website, only on sites we allow, so that customers can use it safely. As a Visitor, I want to ask a question and rate the answer.

[![Publish an Agent and embed it on a website](demo/04-publish-and-embed.jpg)](demo/04-publish-and-embed.mp4)

- **Publish** freezes the Draft as v1 with a note and makes it Live.
- **Embed & limits** gives the one-line Embed Snippet. Adding the shop's origin to the Allowed Origins lets that site show it; the browser refuses any other site.
- The same tab holds rate limits, the daily Token Budget and the widget's text.
- On the shop's own site, a Visitor opens the chat, gets an answer with its Sources and gives it a thumbs-up.

## 5. Iterate safely with Versions, Diffs and revert

> As an Editor, I want every change I publish kept as a Version I can compare and go back to, so that trying an improvement is never a one-way door.

[![Iterate safely with Versions, Diffs and revert](demo/05-versions.jpg)](demo/05-versions.mp4)

- The HR helper's Live History: v1 published, v2 ("shorter answers, without citations") published, reverted to v1, then v3 published.
- Every Version is an immutable snapshot of the Agent's configuration, with its Retrieval Mode and notes.
- Reverting puts an earlier Version Live again without touching the Draft.
- Project Instructions are versioned too.

## 6. Review Conversations and compare Versions

> As an Editor, I want to read what Visitors asked, see which answers they disliked and why, and compare Versions on real numbers, so that I know whether a change made things better.

[![Review Conversations and compare Versions](demo/06-conversations-analytics.jpg)](demo/06-conversations-analytics.mp4)

- Conversations can be filtered by source (Visitors or Playground), Version, feedback, rating and Guardrail outcome. The video filters to Visitor thumbs-down.
- A Conversation shows each reply with the Version that wrote it and its Trace.
- Analytics shows KPIs per Version: volume, tokens, cost, the thumbs-up rate with its 95% interval, fallback rate, Guardrail block rate, searches per reply and latency. v2 is clearly worse than v1.
- **Compare two Versions** sets them side by side, with the configuration changes that explain the difference.

## 7. Choose Automatic or Agentic retrieval

> As an Editor, I want to choose per Agent between one cheap, predictable search and letting the model search the Knowledge Base itself, so that I can trade cost against accuracy where it matters.

[![Choose Automatic or Agentic retrieval](demo/07-agentic-retrieval.jpg)](demo/07-agentic-retrieval.mp4)

- The HR helper is **Automatic**: its Trace shows one up-front search and a single Retrieved Chunks table.
- The Product FAQ is **Agentic**: the model has one read-only tool, Knowledge Search, and a Search limit.
- The Playground shows "Searching: …" with the query the model wrote. The Trace lists each Search with the Chunks it found.
- On the shop page, Visitors see "Searching the knowledge base…", never the model's query.

## 8. See the Guardrails stop prompt injection

> As an Organisation, I want attacks on our Agents stopped, and to see which defence stopped each one, so that a public chat box isn't a liability.

[![See the Guardrails stop prompt injection](demo/08-guardrails.jpg)](demo/08-guardrails.mp4)

- The attack panel (`/demo/attacks.html`) sends real attacks to a demo Agent.
- Instruction override and prompt extraction are blocked by the input Guardrail, a local classifier.
- A base64-encoded attack gets past the classifier. The naive model starts to leak its prompt, and the Canary token replaces the reply.
- A benign question is answered normally.
- Guardrail outcomes are counted in Analytics.

## 9. Manage the team, spending and audit trail

> As an Owner, I want to invite colleagues with the right role, cap and see what our Agents spend, and know who changed what, so that the Organisation stays under control.

[![Manage the team, spending and audit trail](demo/09-team-and-cost.jpg)](demo/09-team-and-cost.mp4)

- **Invite someone** emails an Editor invite (shown arriving in the stack's Mailpit). Its link stays on the page to copy.
- General settings let an Owner require two-factor authentication and set the Retention Window.
- A spent daily Token Budget makes the widget show the Agent's own "unavailable" text.
- Organisation cost shows spend by Project or by Agent, with Visitors and the Playground apart.
- The Audit log filters every change by action, actor and date.

## Regenerating the videos

The recordings come from [`scripts/demo-videos/record.cjs`](../scripts/demo-videos/record.cjs), which drives the Studio with Playwright using the same accessible names as the e2e suite, and [`scripts/demo-videos/encode.sh`](../scripts/demo-videos/encode.sh), which turns them into these MP4s and posters. They need `ffmpeg`.

```sh
make dev                                  # in another terminal
make seed-reset                           # the stories change the demo data, so start fresh
node scripts/demo-videos/record.cjs scripts/demo-videos/out
scripts/demo-videos/encode.sh scripts/demo-videos/out
```

Stories 1 and 2 share the Organisation that story 1 signs up, and story 4 publishes the Agent story 3 creates, so run them together. Pass slugs after the output folder to record only some, for example `node scripts/demo-videos/record.cjs out 07-agentic-retrieval`.
