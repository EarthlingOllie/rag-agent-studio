# Studio screenshots

Snapshots of the Studio as of ticket 03-06 (Tags), captured with Playwright at 1440×900, 2× scale.

| File | Screen |
| --- | --- |
| `01-sign-up.png` | Sign up (creates a Member and their Organisation) |
| `02-sign-in.png` | Sign in |
| `03-projects-empty.png` | Projects, before any exist |
| `04-documents.png` | A Project's Documents tab: upload, Tags, filters, the seed handbook Ready |
| `06-agent-playground.png` | An Agent's Draft beside the Playground, with a streamed answer |
| `07-settings-general.png` | Organisation settings: General |
| `08-members.png` | Members |
| `09-credentials.png` | Provider Credentials |
| `10-models.png` | Models (Default Model) |
| `11-theme.png` | Theme editor with the widget preview |
| `12-audit.png` | Audit Events |
| `13-profile.png` | Profile |

The stack ran with the offline fakes (`MODEL_GATEWAY=fake`, `CREDENTIAL_VERIFIER=fake`,
`EMBEDDER=fake`, `DOCUMENT_CONVERTER=fake`), so the Playground answer is the fake gateway's
reply, not a real retrieval answer. No real provider key was used.

To recapture against a running stack (`make dev`) on a fresh database — the script signs up
`ada@northwind.example`, so it runs once per database:

```sh
node docs/screenshots/capture.cjs   # needs Playwright; E2E_BASE_URL overrides http://localhost:5173
```

There is no `05-` shot: the first set predates the document viewer (ticket 03-03).

## Seeded demo (through ticket 03-02's live-model follow-up, PR #47)

Captured after `make seed`, signed in as the demo Owner. The Default Model is the seed's labelled
demo model, which gives canned answers, so the answers show citations and Traces rather than real model
output. `capture-seeded.cjs` recaptures them (`node docs/screenshots/capture-seeded.cjs docs/screenshots`).

| File | Screen |
| --- | --- |
| `14-projects-seeded.png` | Projects, with the seeded Northwind Handbook |
| `15-documents-seeded.png` | Four Documents (MD, DOCX, PPTX) with Tags, quota, Flagged Chunks and actions |
| `16-document-viewer.png` | Document viewer: converted markdown beside Chunks with heading paths |
| `17-instructions.png` | Instructions tab with the Markdown editor, before publishing |
| `18-instructions-versions.png` | Instructions Versions: v2 Current, history and Revert |
| `19-agents-list.png` | Agents: HR helper and Product FAQ |
| `20-agent-config.png` | Full AgentConfig editor (Behaviour, Model override, Experience, Guardrails) |
| `21-playground-citations.png` | Playground answer with a citation chip and Trace link |
| `22-trace-drawer.png` | Trace drawer: model, tokens, cost, latency, Guardrails, retrieved Chunks |
| `23-models-demo.png` | Models: the demo model as Default Model |
| `24-theme-seeded.png` | The seeded Northwind Theme |
| `25-credentials-seeded.png` | Credentials |
| `26-members-seeded.png` | Members: the demo Owner and Editor |
| `27-audit-seeded.png` | Audit Events from the seed |

## Publishing, embedding and Conversations (through PR #60)

Captured on the seeded demo after the shots above. `capture-live.cjs` publishes the Agents, rolls out
Instructions and embeds HR helper on the demo host page (`apps/widget/host`, port 5175);
`capture-widget.cjs` re-takes just the widget and Conversations shots. Both expect a freshly seeded
database.

| File | Screen |
| --- | --- |
| `28-agent-not-live.png` | An Agent before its first publish: "Not live" and the Publish form |
| `29-agent-published-v1.png` | Published v1 with Instructions v1: now Live |
| `30-live-history.png` | Live History after a second publish |
| `31-version-diff.png` | Versions list and Compare: the Instructions diff between v2 and v3 |
| `32-embed-snippet-origins.png` | Embed: the snippet and Allowed Origins |
| `33-playground-instructions-picker.png` | Playground Instructions picker (Draft or a published Version) |
| `34-rollout-dialog.png` | Roll out Instructions v2 to the Live Agents |
| `35-rollout-results.png` | Rollout results |
| `36-agents-live.png` | Agents list with Live badges and bulk revert |
| `37-widget-on-host.png` | The branded widget on a host page on another origin |
| `38-widget-guardrail-block.png` | The input Guardrail refusing a prompt-injection message |
| `39-conversations.png` | Conversations viewer with filters |
| `40-conversation-detail.png` | One Visitor Conversation, pinned to its Agent Version |

## The Tidepool reskin and the showcase (candidate-reskin, through PR #88)

Captured on `candidate-reskin` after the first seven spec-11 tickets (foundation, colour codemod,
shell and breadcrumb, Project frame, Organisation settings, signed-out pages) and every feature
ticket in slices 06–10. Pages whose reskin tickets are still open (Documents table, Agent views,
Conversations, Analytics) show the new shell around the old content. `capture-reskin.cjs` recaptures
them on a freshly seeded database with the demo host pages running (`make dev`, `make seed`).

| File | Screen |
| --- | --- |
| `41-sign-in-reskin.png` | The reskinned sign-in page |
| `42-projects-reskin.png` | Projects in the new shell: one top bar with the breadcrumb |
| `43-documents-reskin.png` | Documents inside the new Project frame |
| `44-breadcrumb-menu.png` | A breadcrumb level as a switcher menu (Project sections) |
| `45-flagged-chunk.png` | The planted Chunk with its Guardrail flag in the Document viewer |
| `46-agents-list.png` | Agents, including the seeded Guardrail demo and Low-budget helper |
| `47-live-history-seeded.png` | HR helper's seeded Live History: v2 published, reverted, v3 published |
| `48-analytics-v1.png` | Analytics: v1's KPI cards and the time series |
| `49-analytics-v2.png` | Analytics: v2, with the lower Thumbs-up rate |
| `50-analytics-v3-low-confidence.png` | Analytics: v3, marked Low confidence |
| `51-conversations-seeded.png` | Four weeks of seeded Conversations |
| `52-organisation-cost.png` | Organisation cost by Project |
| `53-organisation-settings-reskin.png` | The reskinned Organisation settings |
| `54-audit-seeded.png` | Audit Events from the seeded history |
| `55-demo-shop-widget.png` | The demo shop with the Product FAQ bubble |
| `56-demo-inline.png` | The help centre with the inline layout |
| `57-disallowed-origin.png` | The same snippet on an origin the Agent doesn't allow |
| `58-attack-panel.png` | The attack panel after every button (the last result shown) |
| `59-token-budget-spent.png` | The Low-budget helper after its Token Budget is spent |
| `60-agents-budget-exhausted.png` | The Studio's Agents list showing Budget exhausted |
| `61-documents-dark.png` | Dark Appearance: Documents |
| `62-cost-dark.png` | Dark Appearance: Organisation cost |

These ran with `INJECTION_CLASSIFIER=heuristic` and `INPUT_CLASSIFIER=heuristic` (the local ONNX
model couldn't be downloaded in the capture environment) and the fake embedder, so the scores and
which Chunks rank first differ from a stack built with the bundled models.
