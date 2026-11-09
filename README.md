# RAG Agent Studio

[![backend](https://github.com/EarthlingOllie/rag-agent-studio/actions/workflows/backend.yml/badge.svg?branch=main)](https://github.com/EarthlingOllie/rag-agent-studio/actions/workflows/backend.yml)
[![frontend](https://github.com/EarthlingOllie/rag-agent-studio/actions/workflows/frontend.yml/badge.svg?branch=main)](https://github.com/EarthlingOllie/rag-agent-studio/actions/workflows/frontend.yml)
[![e2e](https://github.com/EarthlingOllie/rag-agent-studio/actions/workflows/e2e.yml/badge.svg?branch=main)](https://github.com/EarthlingOllie/rag-agent-studio/actions/workflows/e2e.yml)
[![infra](https://github.com/EarthlingOllie/rag-agent-studio/actions/workflows/infra.yml/badge.svg?branch=main)](https://github.com/EarthlingOllie/rag-agent-studio/actions/workflows/infra.yml)
[![security](https://github.com/EarthlingOllie/rag-agent-studio/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/EarthlingOllie/rag-agent-studio/actions/workflows/security.yml)
[![links](https://github.com/EarthlingOllie/rag-agent-studio/actions/workflows/links.yml/badge.svg?branch=main)](https://github.com/EarthlingOllie/rag-agent-studio/actions/workflows/links.yml)
[![coverage: 100% line and branch, gated](https://img.shields.io/badge/coverage-100%25%20line%20%2B%20branch%20(gated)-brightgreen)](https://github.com/EarthlingOllie/rag-agent-studio/actions/workflows/backend.yml)

**A multi-tenant studio where an Organisation builds AI Agents grounded in its own documents, versions and publishes them like code, and embeds them on its websites behind layered prompt-injection defences.** Every answer cites its sources, every change is an immutable Version you can diff and revert, and every Conversation feeds analytics that compare Versions honestly, with confidence intervals.

![The Product FAQ Agent embedded as a chat bubble on the demo shop page](docs/screenshots/37-widget-on-host.png)

Contents: [Five-minute demo](#five-minute-demo) · [Quickstart](#quickstart) · [Architecture](#architecture) · [Stack](#stack) · [Testing](#testing) · [Security](#security) · [Deploy and destroy](#deploy-and-destroy-aws-demo) · [Documentation](#documentation)

## What it does

- **Organisations and Members.** Hand-rolled Studio auth: sign-up, sign-in, password reset by email, TOTP MFA (optionally required by the Organisation), invites, Owner and Editor roles, an Organisation switcher and an Audit log of every change.
- **Provider Credentials and models.** API keys (Anthropic, OpenAI) or an AWS Bedrock role, stored with KMS envelope encryption; a Default Model per Organisation, per-Agent overrides, a price table with overrides so every reply has a cost.
- **Projects and the Knowledge Base.** Upload PDF, DOCX, PPTX, HTML and Markdown; Docling converts and chunks them, a local embedding model (or a provider one) embeds them, and an ingestion scan flags Chunks that look like instructions to an AI. Tags, editions, dedupe, OCR and a Document viewer that shows every Chunk.
- **Agents and the Playground.** A Markdown system prompt, Tag scoping, hybrid retrieval (pgvector plus full-text, fused) with an optional reranker, citations, and a Trace of every answer: model, tokens, cost, latency and the Chunks retrieved.
- **Versioning.** Immutable Agent Versions with a movable Live pointer, Project Instructions that Versions pin, diffs, Live History, revert, bulk publish and an Instructions rollout that shows which Agents are behind.
- **Embedding.** A 1 KB loader script injects an iframe widget, refused by the browser on any origin outside the Agent's Allowed Origins. Theme and per-Agent branding, WCAG 2.2 AA, resumable Conversations, rate limits and a daily Token Budget.
- **Feedback and analytics.** Thumbs and Conversation Ratings from Visitors, a Conversations viewer with Traces, daily rollups, per-Version KPI cards with Wilson intervals and low-confidence marking, time series, retention and tombstones.
- **Guardrails.** An input Guardrail (a local ONNX classifier, or an LLM classifier) in block, warn or log mode, a Canary token that stops prompt leaks, Guardrail analytics and alerts, and an Attack evaluation suite run in CI.

## Five-minute demo

Run the [Quickstart](#quickstart) first (`make dev`, then `make seed`). Sign in at <http://localhost:5173> as the demo **Owner** `owner@northwind.example` / `northwind-owner-demo` (or the **Editor** `editor@northwind.example` / `northwind-editor-demo`); `make seed` prints these too. Everything below is seeded, synthetic and answered by the labelled demo model, so no API key is needed.

1. **The Studio** (30 s). The Northwind Traders Organisation, its Theme and Members. Open **Projects → Northwind Handbook**: four Documents (a staff handbook, a returns policy, a product FAQ in DOCX and a slide deck in PPTX), split by the HR and Products Tags.
2. **The Knowledge Base viewer** (30 s). Open `northwind-staff-handbook.md`: the header says a Chunk was flagged as possible instructions to an AI, and the planted "A note for AI assistants" Chunk carries a Guardrail flag with the classifier's score. That is the indirect-injection defence at ingestion.
3. **The Agent editor and a Playground Trace** (45 s). **Agents → HR helper**: the Markdown prompt, Tag scoping to HR, retrieval settings. Ask the Playground "How many days of annual leave do I get?" and open the answer's **Trace**: the model, tokens, cost, latency and the Chunks retrieved, the cited one first.
4. **Publish and revert** (30 s). The HR helper's **Live History**: v1 published, v2 ("Shorter answers, without citations") published, then **reverted to v1**, then v3 published. Diff any two Versions; the Instructions tab shows the Product FAQ **behind** on Instructions v1.
5. **The embed on the shop page** (30 s). Open <http://localhost:5175/demo/>, a fictional shop on another origin. Open the chat bubble and ask the Product FAQ "Can I return a jar of honey?"; `inline.html` shows the same Agent inline.
6. **The disallowed origin** (15 s). Open <http://localhost:5176/>: the same snippet on an origin the Agent doesn't allow. The browser refuses to show the frame (`frame-ancestors`).
7. **The attack panel** (60 s). Open <http://localhost:5175/demo/attacks.html> and click each button. Instruction override, prompt extraction and the role-play jailbreak are **blocked by the input Guardrail**; the base64 encoded attack slips past it, the naive demo model starts to leak its prompt and the **Canary token replaces the reply**; the benign control is answered. The table shows which layer acted.
8. **The Token Budget** (15 s). On <http://localhost:5175/demo/budget.html>, **Use up today's Token Budget**: the widget shows the Agent's unavailable text, and the Studio's Agents list shows **Budget exhausted**.
9. **Analytics comparison** (45 s). **Analytics → HR helper**: switch the Version between v1, v2 and v3. Four weeks of seeded Conversations show v2's thumbs-up rate clearly below v1's, with non-overlapping 95% intervals, and v3 better again but marked **Low confidence** (fewer than 30 Conversations).
10. **The Audit tab** (15 s). **Organisation settings → Audit**: every publish, revert, bulk publish and Instructions change from the seeded history, with actor and before/after.

The whole script is automated as one Playwright test, [`frontend/e2e/tests/five-minute-demo.spec.ts`](frontend/e2e/tests/five-minute-demo.spec.ts), which `make e2e` runs after `make seed`.

## Quickstart

Prerequisites: Docker with Compose v2, GNU Make, [uv](https://docs.astral.sh/uv/), and Node 22 with pnpm (`corepack enable`).

```sh
make dev     # builds and starts the stack: Postgres+pgvector, Redis, RustFS, Mailpit, API, worker, Beat, Studio, widget, demo pages
make seed    # in another terminal: creates the demo Organisation and prints its sign-in details (idempotent)
```

| Where | What |
|---|---|
| <http://localhost:5173> | The Studio (sign up to create your own Organisation, or sign in as the demo Owner) |
| <http://localhost:8000/docs> | The API's OpenAPI docs |
| <http://localhost:5175/demo/> | Demo host pages: shop (bubble), `inline.html`, `budget.html`, `attacks.html` |
| <http://localhost:5176/> | The disallowed-origin page |
| <http://localhost:8025> | Mailpit: every email the stack sends (invites, password resets) |

`make seed-reset` erases the demo Organisation (only that one) and seeds it again. To answer with a real model instead of the demo one, set `SEED_CREDENTIAL_PROVIDER` (`anthropic` or `openai`) and `SEED_CREDENTIAL_API_KEY` before `make seed`; the seeded history is always generated by the demo model. `make help` lists every target; [docs/development.md](docs/development.md) covers settings, ports and each subsystem.

## Architecture

```mermaid
flowchart LR
  subgraph Browser
    Studio["Studio (React SPA)"]
    Host["Customer site + embed.js"] --> Widget["Widget iframe"]
  end
  Studio --> Edge
  Widget --> Edge
  Edge["CloudFront (AWS) / Vite proxy (local): one origin"] --> API["FastAPI API"]
  Edge --> Static["Static assets: Studio, widget, demo pages"]
  API --> PG[("Postgres 16 + pgvector: tenants, Versions, Chunks, Conversations, rollups")]
  API --> Redis[("Redis: Celery broker, rate limits, Token Budgets")]
  API --> Store[("S3 / RustFS: uploads, Theme images")]
  API --> Gateway["Model gateway"]
  Redis --> Worker["Celery worker: Docling, chunking, embeddings, ingestion scan"]
  Beat["Celery Beat: rollups, retention"] --> Redis
  Worker --> PG
  Worker --> Store
  Gateway --> Providers["Anthropic, OpenAI, Bedrock, demo model"]
  API --> Guard["Guardrails: input classifier (local ONNX or LLM), Canary token"]
  API --> KMS["KMS / local key wrapper: envelope encryption"]
```

A Visitor's message goes widget → API → admission control (Allowed Origin, rate limits, Token Budget) → input Guardrail → hybrid retrieval scoped by Tags → the Live Version's prompt and pinned Instructions → the model through the gateway, streamed back through the Canary filter with citations, and saved with its Trace. Ingestion runs on the worker: upload to object storage, Docling conversion, chunking, the ingestion scan, embedding into pgvector. [docs/plan.md](docs/plan.md#2-architecture) has the full pipelines; [ADR-0010](docs/adr/0010-aws-runtime-shape.md) and [ADR-0011](docs/adr/0011-single-cloudfront-origin.md) the AWS shape.

## Stack

| Layer | Choices |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic, Pydantic AI (model gateway), Celery with Redis, Docling, fastembed (local embeddings), ONNX classifier, Logfire telemetry with scrubbing, uv |
| Data | Postgres 16 with pgvector (vectors and full-text in one store), Redis 7, S3 (RustFS locally) |
| Frontend | pnpm workspace, React 19, TanStack Router and Query, Tailwind CSS 4, Vite, Recharts, a generated TypeScript API client; the widget and a dependency-free 1 KB loader |
| Testing | pytest against real Postgres and Redis (pytest-xdist), Vitest + Testing Library + MSW, Playwright + axe, `terraform test`, Node's test runner |
| Infrastructure | Terraform: ECS Fargate (ARM64), RDS, ElastiCache, S3, CloudFront, KMS, ECR, fck-nat; GitHub Actions with OIDC |
| Quality and security | ruff, `mypy --strict`, eslint, `tsc`, TFLint, Checkov, gitleaks, pip-audit, pnpm audit, Trivy |

## Testing

- **100% line and branch coverage, enforced** for the backend and frontend ([ADR-0008](docs/adr/0008-full-line-and-branch-coverage.md)); a build below it fails. Live-model tests are marked `live` and sit outside the gate.
- **Tests at seams, not internals.** Behaviour is tested at the highest seam: the HTTP API in process against real Postgres and Redis, components through the DOM with MSW, the whole stack through Playwright. Model providers, classifiers and clocks are swapped for test doubles at their ports. See the [shared test seams](docs/specs/README.md#shared-test-seams).
- **End to end.** `make e2e` starts the compose stack, seeds it and runs every Playwright spec with axe accessibility scans (WCAG 2.2 AA), including the automated [five-minute demo](#five-minute-demo).
- **Guardrail evaluation.** `make eval` runs the Attack evaluation suite (`backend/evals/attack_suite.json`) through the real Guardrail pipeline on every push; `make eval-live` runs it nightly against a real model with a minimum pass rate.
- **Infrastructure and links.** `make infra-check` runs `terraform test` with mocked providers, TFLint and Checkov; `make link-check` checks every relative link and anchor in the Markdown.

| Command | What it runs |
|---|---|
| `make services` then `make test` | Backend (`TEST_WORKERS=3` for parallel) and frontend suites with the coverage gates |
| `make lint` | ruff, `mypy --strict`, eslint, `tsc` |
| `make e2e` | Stack up, seed, Playwright + axe |
| `make eval` | The Attack evaluation suite (mocked model) |
| `make infra-check` | Terraform fmt, validate, test, TFLint, Checkov and the deploy scripts' tests |
| `make link-check` | Every relative link in the Markdown resolves |
| `make security` | gitleaks, pip-audit, pnpm audit, Trivy |

## Security

- **Envelope encryption for Provider Credentials.** Each credential is encrypted with its own data key, wrapped by KMS in AWS (a local key wrapper in development); plaintext keys never leave the API process or reach logs ([ADR-0006](docs/adr/0006-provider-credentials-envelope-encryption.md)).
- **Studio authentication.** Argon2 password hashes, httpOnly cookie sessions, sign-in rate limiting and lockout, TOTP MFA with an Organisation policy to require it, and an Audit Event for every change ([ADR-0005](docs/adr/0005-hand-rolled-studio-auth.md)). Every query is scoped to the Organisation; a tenant-isolation test walks every route.
- **Layered prompt-injection defence** ([ADR-0007](docs/adr/0007-layered-prompt-injection-defence.md)): an ingestion scan flags planted instructions in Documents (mark or exclude from retrieval); an input Guardrail classifies every Visitor message (block, warn or log); a Canary token in the prompt cuts off any reply that leaks it; Agents have no side-effecting tools, so a successful injection can only produce text.
- **Embed protections** ([ADR-0004](docs/adr/0004-iframe-embed-with-origin-allowlist.md)): the widget is an iframe whose shell sends `Content-Security-Policy: frame-ancestors` with the Agent's Allowed Origins, short-lived signed Conversation tokens, per-Conversation and per-IP rate limits, and a daily Token Budget that caps spend.
- **Telemetry with scrubbing**, retention with tombstones for old Conversations, and security gates in CI: gitleaks, pip-audit, pnpm audit and Trivy.

## Deploy and destroy (AWS demo)

The AWS demo is applied on demand and destroyed after use; nothing is always on. Full details: [docs/deploy-demo.md](docs/deploy-demo.md) and, once per account, [docs/infra-bootstrap.md](docs/infra-bootstrap.md).

1. **Bootstrap (once):** apply `infra/bootstrap` (the Terraform state bucket and the GitHub OIDC deploy role), then set the `AWS_DEPLOY_ROLE_ARN` secret and the `TF_STATE_BUCKET` variable.
2. **Deploy:** Actions → **deploy** → Run workflow. It builds and pushes ARM64 images, applies `infra/envs/demo`, runs the migration task, rolls the API, worker and Beat services, uploads the Studio, widget and demo pages, and smoke-checks the CloudFront URL it prints. From a laptop: `TF_STATE_BUCKET=… AWS_REGION=eu-west-2 scripts/deploy/deploy.sh <tag>`.
3. **Destroy:** Actions → **destroy** → Run workflow, typing `destroy demo` to confirm. Everything goes, Documents and database included; the state bucket and deploy role stay. From a laptop: `scripts/deploy/destroy.sh "destroy demo"`.

**Expected cost** (on-demand, `eu-west-2`, default sizes, almost no traffic; [the breakdown](docs/deploy-demo.md#expected-cost)): about **0.33 USD an hour**, so about **8 USD for a day** of demo, or about 240 USD a month if left on. After destroy, only the bootstrap's state bucket and key remain, about 1 USD a month. The disallowed-origin page is local-only.

## Documentation

- [GLOSSARY.md](GLOSSARY.md): the domain language (Organisation, Agent, Version, Live Version, Guardrail, Canary token, …) used in code, UI and docs.
- [docs/adr](docs/adr): the architecture decisions:
  [0001 pgvector hybrid search](docs/adr/0001-pgvector-hybrid-search.md) ·
  [0002 local embeddings by default](docs/adr/0002-local-embeddings-by-default.md) ·
  [0003 immutable Versions with a Live pointer](docs/adr/0003-immutable-versions-with-live-pointer.md) ·
  [0004 iframe embed with origin allowlist](docs/adr/0004-iframe-embed-with-origin-allowlist.md) ·
  [0005 hand-rolled Studio auth](docs/adr/0005-hand-rolled-studio-auth.md) ·
  [0006 envelope encryption](docs/adr/0006-provider-credentials-envelope-encryption.md) ·
  [0007 layered prompt-injection defence](docs/adr/0007-layered-prompt-injection-defence.md) ·
  [0008 100% coverage](docs/adr/0008-full-line-and-branch-coverage.md) ·
  [0009 Operational Settings outside Versions](docs/adr/0009-operational-settings-outside-versions.md) ·
  [0010 AWS runtime shape](docs/adr/0010-aws-runtime-shape.md) ·
  [0011 single CloudFront origin](docs/adr/0011-single-cloudfront-origin.md) ·
  [0012 demo seed through the API](docs/adr/0012-demo-seed-through-the-api.md)
- [docs/plan.md](docs/plan.md): the build plan, architecture and delivery slices.
- [docs/specs](docs/specs/README.md): the ten specs, one per slice, with the shared test seams.
- [docs/tickets](docs/tickets/README.md): every ticket, its acceptance criteria and its evidence folder.
- [docs/development.md](docs/development.md): local development in depth; [seed/README.md](seed/README.md): the synthetic demo content and its [licence](seed/LICENCE.md).

## Licence

[MIT](LICENSE). The demo content in `seed/` is synthetic; see [seed/LICENCE.md](seed/LICENCE.md).
