# 01: Walking skeleton

**Ticket:** `01-01` · **Spec:** [Skeleton, CI, auth and tenancy](../../specs/01-skeleton-auth-tenancy-spec.md)

**What to build:** A developer clones the repo, starts the whole stack with one command, and opens a Studio page that shows the API's health, fetched through the TypeScript client generated from the backend's OpenAPI schema. A Celery health task runs on the worker. Backend and frontend CI already enforce 100% line and branch coverage, and fail if the committed API client is out of date.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] One command starts Postgres with pgvector, Redis, RustFS, Mailpit, the API, the worker, Beat and the Studio
- [ ] Make targets exist for dev, test, lint and client generation
- [ ] Settings are typed and validated at startup; a missing required setting fails fast with a clear message
- [ ] A Studio page shows API health through the generated client, and a Celery health task completes a round trip
- [ ] Alembic is configured, with an upgrade-to-head / downgrade-to-base round-trip test
- [ ] Backend and frontend CI workflows run lint, type checks and tests, and fail below 100% line or branch coverage
- [ ] CI fails when the committed API client differs from a fresh generation
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
