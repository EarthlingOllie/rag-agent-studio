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
