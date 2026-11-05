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

There is no `05-` shot yet: the document viewer arrives with ticket 03-03.
