# 03: Telemetry with scrubbing

**Ticket:** `01-03` · **Spec:** [Skeleton, CI, auth and tenancy](../../specs/01-skeleton-auth-tenancy-spec.md)

**What to build:** API, worker and database activity is traced with OpenTelemetry through the Logfire SDK. Traces are exported to Logfire when a token is configured and to the console otherwise. Nothing exported can contain Message text, cookies, authorisation headers or secrets.

**Blocked by:**
- [01-01: Walking skeleton](01-walking-skeleton.md)

**Status:** ready-for-agent

- [ ] FastAPI, SQLAlchemy, Celery and HTTP client instrumentation is enabled
- [ ] The exporter is chosen by settings: Logfire when a token is present, console otherwise
- [ ] A scrubbing processor removes Message bodies, cookies, authorisation headers and secret-like attributes
- [ ] A test captures spans with an in-memory exporter and proves the scrubbing works
- [ ] Services emit structured JSON logs
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
