# 02: Seeded history

**Ticket:** `10-02` · **Spec:** [Seed data and showcase](../../specs/10-seed-showcase-spec.md)

**What to build:** The demo Organisation has a believable history: two Agents with Tag scoping, Version history including a revert, Instructions with one Agent behind, and several weeks of Conversations, feedback and ratings that make the comparison charts tell a story.

**Blocked by:**
- [10-01: Seed foundation](01-seed-foundation.md)
- [05-05: Bulk publish, bulk revert and Instructions rollout](../05-versioning-project-instructions/05-bulk-publish-revert.md)
- [07-04: Rollups and Version KPIs](../07-feedback-logging-comparison/04-rollups-version-kpis.md)

**Status:** ready-for-agent

- [ ] There's an HR Agent and a FAQ Agent with Tag scoping; HR has v1 to v3, with v2 reverted
- [ ] Instructions have v1 and v2, with one Agent behind
- [ ] Weeks of Conversations are generated through the runtime with a `FunctionModel`, timestamps are backfilled, and feedback and ratings come from a fixed random seed that makes v2 worse; one Version has a small sample
- [ ] Rollups run for every historical day, and Audit Events are present
- [ ] An API-level test asserts what an interviewer would see
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
