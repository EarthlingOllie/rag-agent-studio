# Demo

Screen recordings of eight core user journeys through RAG Agent Studio, then a five-minute walkthrough you can follow on your own machine. Everything shown runs locally against the seeded **Northwind Traders** demo Organisation (`make dev`, then `make seed`; see the [Quickstart](../README.md#quickstart)). The content is synthetic, and answers come from a clearly labelled demo model unless a real provider key is configured.

| # | Journey | What it shows |
|---|---|---|
| 1 | [Build a Knowledge Base](#1-build-a-knowledge-base) | Document ingestion, chunking, and indirect prompt-injection detection |
| 2 | [Create an Agent and test it in the Playground](#2-create-an-agent-and-test-it-in-the-playground) | Prompting, Tag scoping, citations and the Trace |
| 3 | [Automatic versus Agentic retrieval](#3-automatic-versus-agentic-retrieval) | A fixed RAG pipeline against a model that decides when and how to search |
| 4 | [Version, publish, compare and revert](#4-version-publish-compare-and-revert) | Shipping Agents like code |
| 5 | [Embed the Agent on a website](#5-embed-the-agent-on-a-website) | The widget, Allowed Origins and the browser refusing other sites |
| 6 | [Defend against prompt injection](#6-defend-against-prompt-injection) | The input Guardrail, the Canary token and Token Budgets under attack |
| 7 | [Measure quality and cost](#7-measure-quality-and-cost) | Comparing Versions with confidence intervals, Conversations and spend |
| 8 | [Run an Organisation securely](#8-run-an-organisation-securely) | Members and roles, MFA, encrypted credentials, models and the Audit log |

---

## 1. Build a Knowledge Base

Upload documents into a Project and watch them become searchable Chunks.

- Upload PDF, DOCX, PPTX, HTML and Markdown files; a Celery worker converts and chunks them with Docling and embeds them into pgvector.
- Tag Documents (here, **HR** and **Products**) so each Agent only retrieves what it should.
- Open the Document viewer to see every Chunk beside the source. The staff handbook contains a planted "A note for AI assistants" section: the ingestion scan has flagged it as possible instructions to an AI, with the classifier's score, so it can be marked or kept out of retrieval.

<!-- Recording 1: paste the GitHub video URL on its own line here. -->

![The Document viewer, a flagged Chunk among the Chunks](screenshots/67-document-viewer-light.png)

## 2. Create an Agent and test it in the Playground

Configure an Agent and see exactly how it reaches each answer.

- Write the system prompt in Markdown, scope retrieval to the **HR** Tag, and tune retrieval and model settings, including a per-Agent model override.
- Ask the Playground *"How many days of annual leave do I get?"*. The answer streams back with citations to the handbook.
- Open the **Trace**: the model, tokens, cost and latency, and every Chunk retrieved, with the cited one first.

<!-- Recording 2: paste the GitHub video URL on its own line here. -->

![An Agent's Playground beside its configuration](screenshots/70-agent-playground-light.png)

## 3. Automatic versus Agentic retrieval

The same Knowledge Base, two retrieval strategies, and the trade-off between them.

- **HR helper** is *Automatic*: one search on the user's exact words before the model is called. One model call, cheap and predictable.
- **Product FAQ** is *Agentic*: the model has a search tool. Asked *"Can I return a jar of honey?"*, the Playground shows **Searching: …** as the model writes its own query, and the Trace lists each search with the query and the Chunks it returned.
- The Trace makes the cost visible: two model calls and more tokens, in exchange for the model choosing whether, how often and with what words to search.

<!-- Recording 3: paste the GitHub video URL on its own line here. -->

![A Conversation with its Trace](screenshots/73-conversation-light.png)

## 4. Version, publish, compare and revert

Agents change safely, with a full history.

- Publishing creates an immutable Version and moves the **Live** pointer to it; editing never touches what Visitors see.
- **Live History** for HR helper: v1 published, v2 (*"Shorter answers, without citations"*) published, reverted to v1, then v3 published.
- Diff any two Versions side by side, and see in the Instructions rollout which Agents are behind the Project's latest Instructions, then bulk-publish them.

<!-- Recording 4: paste the GitHub video URL on its own line here. -->

![An Agent's Versions: Live History, Versions and Compare](screenshots/71-agent-versions-light.png)

## 5. Embed the Agent on a website

From the Studio to a customer's website with a one-line snippet.

- Copy the embed snippet and set the Agent's **Allowed Origins**, branding and limits.
- On the demo shop (<http://localhost:5175/demo/>), open the chat bubble and ask the Product FAQ a question. Visitors see *"Searching the knowledge base…"*, never the model's query, then a cited answer. `inline.html` shows the same Agent inline.
- On <http://localhost:5176/>, the same snippet on a site that isn't allowed: the browser refuses to render the frame (`frame-ancestors`).

<!-- Recording 5: paste the GitHub video URL on its own line here. -->

![The Product FAQ Agent in the chat bubble on the demo shop page](screenshots/37-widget-on-host.png)

## 6. Defend against prompt injection

Live attacks against the embedded Agent, and which defence stopped each one.

- On the attack panel (<http://localhost:5175/demo/attacks.html>), instruction override, prompt extraction and a role-play jailbreak are **blocked by the input Guardrail**.
- A base64-encoded attack slips past the classifier and the naive demo model starts to leak its prompt; the **Canary token** detects the leak and replaces the reply. A benign control question is answered normally.
- On `budget.html`, using up the day's **Token Budget** switches the widget to the Agent's unavailable message, and the Studio marks the Agent **Budget exhausted**.

<!-- Recording 6: paste the GitHub video URL on its own line here. -->

![The attack panel, showing which layer acted on each attack](screenshots/58-attack-panel.png)

## 7. Measure quality and cost

Decide which Version is better with evidence, not anecdotes.

- **Analytics → HR helper**: four weeks of seeded Conversations. v2's thumbs-up rate is clearly below v1's, with non-overlapping 95% Wilson intervals; v3 is better again but marked **Low confidence** (fewer than 30 Conversations).
- Open the Conversations viewer to read any Conversation with its Visitor feedback and Trace.
- **Cost** shows what each Project spent, with Visitors and the Playground in separate columns, and breaks down by Agent.

<!-- Recording 7: paste the GitHub video URL on its own line here. -->

![Per-Version analytics with confidence intervals](screenshots/74-analytics-light.png)

## 8. Run an Organisation securely

The multi-tenant administration around the AI.

- Sign up, create an Organisation and invite Members as **Owner** or **Editor**; invite emails arrive in Mailpit.
- Turn on TOTP MFA, and optionally require it for everyone in the Organisation.
- Add provider credentials (Anthropic, OpenAI or an AWS Bedrock role), stored with envelope encryption, and choose the Default Model and its prices.
- Every publish, revert, credential change and Member change lands in the **Audit** log with actor and before/after.

<!-- Recording 8: paste the GitHub video URL on its own line here. -->

![Profile security: TOTP MFA](screenshots/84-security-light.png)

---

## Five-minute walkthrough

Run the [Quickstart](../README.md#quickstart) first (`make dev`, then `make seed`), or use a seeded [AWS demo](../README.md#deploy-and-destroy-aws-demo) at its CloudFront URL. Sign in at <http://localhost:5173> as the demo **Owner** `owner@northwind.example` / `northwind-owner-demo` (or the **Editor** `editor@northwind.example` / `northwind-editor-demo`). No API key is needed.

1. **The Studio** (30 s). The Northwind Traders Organisation, its Theme and Members. Open **Projects → Northwind Handbook**: four Documents (a staff handbook, a returns policy, a product FAQ in DOCX and a slide deck in PPTX), split by the HR and Products Tags.
2. **The Knowledge Base viewer** (30 s). Open `northwind-staff-handbook.md`: the header says a Chunk was flagged as possible instructions to an AI, and the planted "A note for AI assistants" Chunk carries a Guardrail flag with the classifier's score.
3. **The Agent editor and two Playground Traces** (75 s). **Agents → HR helper** (Automatic): ask "How many days of annual leave do I get?" and open the **Trace**. Then **Agents → Product FAQ** (Agentic): ask "Can I return a jar of honey?" and see **Searching: …** before the answer, and **Search 1** in the Trace with the query the model wrote.
4. **Publish and revert** (30 s). HR helper's **Live History**: v1, v2, reverted to v1, then v3. Diff any two Versions; the Instructions tab shows the Product FAQ **behind** on Instructions v1.
5. **The embed on the shop page** (30 s). Open <http://localhost:5175/demo/>, open the chat bubble and ask the Product FAQ "Can I return a jar of honey?"; `inline.html` shows the same Agent inline.
6. **The disallowed origin** (15 s). Open <http://localhost:5176/>: the browser refuses to show the frame (`frame-ancestors`).
7. **The attack panel** (60 s). Open <http://localhost:5175/demo/attacks.html> and click each button; the table shows which layer acted.
8. **The Token Budget** (15 s). On <http://localhost:5175/demo/budget.html>, **Use up today's Token Budget**; the Studio's Agents list then shows **Budget exhausted**.
9. **Analytics comparison** (45 s). **Analytics → HR helper**: switch between v1, v2 and v3 and compare the intervals.
10. **Organisation cost** (15 s). **Cost**: spend per Project; **Break down by → Agent** splits it per Agent.
11. **The Audit tab** (15 s). **Organisation settings → Audit**: every publish, revert, bulk publish and Instructions change, with actor and before/after.

This walkthrough is automated as one Playwright test, [`five-minute-demo.spec.ts`](../frontend/e2e/tests/five-minute-demo.spec.ts), which `make e2e` runs after `make seed`. Step 6 is local-only.
