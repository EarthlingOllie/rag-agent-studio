# 05: Bulk publish, bulk revert and Instructions rollout

**Ticket:** `05-05` · **Spec:** [Versioning and Project Instructions](../../specs/05-versioning-project-instructions-spec.md)

**What to build:** Publishing Project Instructions opens a dialog to roll the new Version out to the Project's Agents. Bulk publish builds from each Agent's Live config, never its Draft. Editors can bulk-revert Agents and see which ones are behind the Current Instructions.

**Blocked by:**
- [05-03: Revert via Live History](03-revert-live-history.md)

**Status:** ready-for-agent

- [ ] Bulk publish uses Live config plus the chosen Instructions Version, never the Draft, and skips Agents that have never been published
- [ ] Each Agent is processed in its own transaction, with a result per Agent
- [ ] Agents with Draft changes are badged in the dialog
- [ ] Publishing Instructions opens the dialog with Agents pre-selected, and "N Agents behind" is shown
- [ ] Reverting Instructions offers a bulk revert of the Agents pinned to the reverted Version
- [ ] The Agent list supports multi-select bulk revert
- [ ] A bulk operation ID is recorded on Live History and Audit Events
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
