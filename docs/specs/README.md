# Slice specs

One spec per delivery slice in [`docs/plan.md`](../plan.md), split into tickets under [`docs/tickets/`](../tickets/README.md). Specs use the vocabulary in [`GLOSSARY.md`](../../GLOSSARY.md) and follow the ADRs in [`docs/adr/`](../adr).

| # | Spec |
|---|---|
| 01 | [Skeleton, CI, auth and tenancy](./01-skeleton-auth-tenancy-spec.md) |
| 02 | [Provider Credentials and Theme](./02-provider-credentials-theme-spec.md) |
| 03 | [Projects and Knowledge Base](./03-projects-knowledge-base-spec.md) |
| 04 | [Agents, retrieval and Playground](./04-agents-retrieval-playground-spec.md) |
| 05 | [Versioning and Project Instructions](./05-versioning-project-instructions-spec.md) |
| 06 | [Embed, widget and Operational Settings](./06-embed-widget-operational-settings-spec.md) |
| 07 | [Feedback, logging and comparison](./07-feedback-logging-comparison-spec.md) |
| 08 | [Guardrails and evaluation](./08-guardrails-evaluation-spec.md) |
| 09 | [Terraform and deploy](./09-terraform-deploy-spec.md) |
| 10 | [Seed data and showcase](./10-seed-showcase-spec.md) |
| 11 | [Studio design system and reskin](./11-studio-design-spec.md) |
| 12 | [Reskin fixes and sidebar navigation](./12-reskin-fixes-sidebar-navigation-spec.md) |
| 13 | [Agentic retrieval](./13-agentic-retrieval-spec.md) |

## Shared test seams

Every spec tests at the **highest seam available** and uses as few seams as possible (ADR-0008). Specs refer to these by name.

### Backend

- **API seam** (the primary one): tests drive the FastAPI application through an in-process async HTTP client, exactly as the Studio or widget would. They use real Postgres with pgvector and real Redis (service containers in CI, `docker compose` locally). Assertions are about HTTP responses and about state that can be observed back through the API. Tests don't reach into tables unless the behaviour has no API surface, such as a purge job.
- **Task seam:** Celery tasks run eagerly in tests and are triggered through the API action that enqueues them (for example, uploading a Document). Beat jobs are called directly as tasks.
- **Adapter fakes:** external systems sit behind a small set of ports. Each port has one production adapter and one deterministic fake, selected by settings or dependency overrides. These are the *only* things tests fake:

| Port | Production adapter | Test fake |
|---|---|---|
| Chat model | Pydantic AI provider models | Pydantic AI `TestModel` / `FunctionModel` |
| Document converter | Docling | Fake converter returning fixed markdown and structure |
| Embedder | Local `multilingual-e5-small`, Voyage, OpenAI, Bedrock | Deterministic hash-based embedder |
| Injection classifier | Local ONNX model, LLM classifier | Rule-driven fake |
| Credential verifier | Live provider call | Fake returning success or a chosen failure |
| Key wrapper | AWS KMS | Local static-key wrapper (also used in `docker compose`) |
| Object store | S3 | RustFS in integration tests; in-memory fake in unit tests |
| Mailer | SES | In-memory outbox; Mailpit in `docker compose` |
| Clock | System clock | Controllable clock |

- **Live suite:** tests marked `live` call real providers and real Docling. They run nightly and on demand, outside the coverage gate.

### Frontend

- **Network seam:** Studio and widget tests render routes and components with Testing Library and mock the API at the network layer with MSW. Handlers are typed with the generated API client. Tests assert on what a person sees and does, not on component internals.
- **End-to-end seam:** Playwright runs against the full `docker compose` stack, with the backend using the fake chat model, plus axe accessibility checks.

### Infrastructure

- **Module seam:** `terraform test` runs against each module's inputs and outputs, alongside `fmt`, `validate`, `tflint` and `checkov`.
