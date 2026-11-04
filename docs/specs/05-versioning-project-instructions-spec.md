# Spec 05: Versioning and Project Instructions

## Problem Statement

Once an Agent is in front of Visitors, every change is a risk. A tweak to the system prompt or a new model can quietly make answers worse, and a change to Project Instructions affects every Agent in the Project at once. Editors need to know exactly what configuration served any given answer, to ship changes deliberately, and to undo a bad change in seconds. When Project Instructions change, they need to roll the change out across many Agents without editing each one by hand, and without accidentally shipping half-finished Draft edits along with it.

## Solution

Agents and Project Instructions each have one editable Draft and an append-only list of immutable, numbered Versions:
- **Publishing an Agent** freezes its Draft into a new Version that pins one Project Instructions Version (the Current Version by default) and makes it the Agent's Live Version.
- **Reverting** moves the Live Version back one step in the Agent's Live History, which restores both its configuration and the Instructions it ran with.
- **Publishing Project Instructions** makes a new Current Version and opens a bulk dialog to roll it out to the Project's Agents. That creates new Agent Versions from each Agent's *Live* configuration plus the new Instructions, never from its Draft.
- **Bulk revert** steps several Agents back at once.

The Studio shows which Agents are behind the Current Instructions, which have unpublished Draft changes, the full Version history with diffs, and who did what in the Audit log.

## User Stories

1. As an Editor, I want to publish an Agent's Draft as a new numbered Version, so that what Visitors get is a deliberate, frozen configuration.
2. As an Editor, I want to add a short note when I publish, so that the history explains why each Version exists.
3. As an Editor, I want publishing to make the new Version the Agent's Live Version immediately, so that shipping is one action.
4. As an Editor, I want each Agent Version to pin the Project Instructions Version it was published with, so that a Version fully describes the Agent's behaviour.
5. As an Editor, I want new Agent Versions to pin the Current Instructions Version by default, so that publishing normally picks up the latest shared rules.
6. As an Editor, I want to choose a different Instructions Version when publishing, so that I can hold an Agent on older Instructions deliberately.
7. As an Editor, I want Versions to be impossible to edit, so that metrics and Traces always point to the configuration that actually served them.
8. As an Editor, I want to see an Agent's Version list with number, author, time, note, pinned Instructions Version and whether it's Live, so that I understand its history at a glance.
9. As an Editor, I want to see the Live History (every time the Live Version changed, by whom, and whether it was a publish or a revert), so that I can reconstruct what Visitors experienced over time.
10. As an Editor, I want to compare any two Versions as a diff of every configuration field and the pinned Instructions, so that I can see exactly what changed.
11. As an Editor, I want to compare the Draft against the Live Version, so that I can review my changes before publishing.
12. As an Editor, I want to revert an Agent, so that the Live Version returns to the one that was Live before, restoring its configuration and its Instructions.
13. As an Editor, I want revert to follow the Live History rather than version numbers, so that a Version that was published and immediately reverted is skipped correctly.
14. As an Editor, I want to be told when there's nothing to revert to, so that I'm not confused by a disabled action.
15. As an Editor, I want to start a new Draft from any past Version, so that I can build on an earlier configuration without reverting.
16. As an Editor, I want the Agent page to show "has unpublished changes" when the Draft differs from the Live Version, so that I don't forget pending work.
17. As an Editor, I want to discard the Draft back to the Live Version, so that I can abandon experiments cleanly.
18. As an Editor, I want an Agent with no published Version to be clearly "not live", so that I know it can't serve Visitors yet.
19. As an Editor, I want to publish Project Instructions as a new Version that becomes the Current Version, so that shared rules are versioned like Agents.
20. As an Editor, I want publishing Project Instructions to open a bulk dialog with the Project's Agents pre-selected, so that rolling out new Instructions is one step.
21. As an Editor, I want to deselect Agents in the bulk dialog, so that I can roll out to some Agents and keep others on older Instructions.
22. As an Editor, I want bulk publish to build each new Agent Version from that Agent's Live configuration plus the chosen Instructions, so that unreviewed Draft edits are never shipped by accident.
23. As an Editor, I want Agents with unpublished Draft changes badged in the bulk dialog, so that I know those edits aren't included.
24. As an Editor, I want Agents that have never been published excluded from bulk publish with an explanation, so that I don't make a first Version without reviewing it.
25. As an Editor, I want bulk results reported per Agent (succeeded, skipped with reason, failed), so that I know the final state of each.
26. As an Editor, I want a bulk action to apply in one transaction per Agent, so that a failure on one Agent never leaves another half-updated.
27. As an Editor, I want to revert Project Instructions, so that the Current Version goes back to the previous one, and then be offered a bulk revert for Agents pinned to the reverted Version.
28. As an Editor, I want to select several Agents from the Agent list and revert them together, so that I can roll back a bad rollout quickly.
29. As an Editor, I want to see "N Agents behind" on the Project Instructions page, and which Instructions Version each Agent pins, so that partial rollouts are visible.
30. As an Editor, I want the Project Instructions Version history with diffs, so that I can see how shared rules have changed.
31. As an Editor, I want to pick an Instructions Version in the Playground (defaulting to the Instructions Draft), so that I can test new Instructions with an Agent before publishing either.
32. As an Editor, I want every Message to record the Agent Version (or Draft) that produced it, so that Traces and analytics have exact attribution.
33. As an Owner, I want every publish, revert and bulk action recorded as an Audit Event with the Versions involved, so that releases are fully traceable.
34. As an Editor, I want two Editors publishing at the same moment to produce two distinct Versions or a clear conflict message, so that history is never corrupted.

## Implementation Decisions

- **Versioning module.** A deep module used by both Agents and Project Instructions. Shared shape: a Draft, an append-only Version list (number assigned per owner, monotonically and race-safely), and a pointer. For Agents the pointer is the Live Version; for Project Instructions it's the Current Version. Operations: publish, revert, start Draft from a Version, discard Draft, diff two snapshots (structural diff of AgentConfig fields plus a text diff for markdown fields).
- **Agent Version.** Number, snapshot of AgentConfig, pinned Project Instructions Version ID, author, note, created time. Immutable: the database refuses updates (trigger or a revoked update privilege) as defence in depth.
- **Live History.** An append-only log per Agent: from-Version, to-Version, action (publish, revert, bulk publish, bulk revert), actor, time, bulk operation ID. Revert sets the Live Version to the from-Version of the most recent entry that moved Live onto the current Version. This is defined precisely so that publish → revert → revert behaves predictably: the second revert follows the history further back rather than toggling.
- **Project Instructions.** Draft (markdown), Versions (number, markdown, author, note), Current Version pointer on the Project. Spec 04's single Instructions field migrates to become the Draft, and an initial v1 is created if the field wasn't empty.
- **Bulk operations.** One request covers several Agents in a Project and an action (publish with an Instructions Version, or revert). Each Agent is processed in its own transaction, under a per-Agent lock (row-level `SELECT … FOR UPDATE`). Bulk publish sources the config from the Agent's Live Version, never its Draft (ADR-0003). The result is a list of per-Agent outcomes, and the operation ID is recorded on Live History and Audit Events.
- **Runtime contract.** Callers resolve "what to run": for a Visitor, the Live Version's AgentConfig and its pinned Instructions text; for the Playground, the Draft AgentConfig plus the chosen Instructions (Draft or a specific Version). The runtime from spec 04 is unchanged. Messages store the Agent Version ID, or null with a Draft marker in the Playground. The Instructions Version is derivable from the Agent Version; Playground Messages store the Instructions Version or Draft marker explicitly.
- **Concurrency.** Publishing locks the Agent row. Version numbers are allocated inside the lock. A Draft edit carries an optimistic concurrency token (`updated_at` or a revision number), and a stale save returns 409 with the latest Draft.
- **API.**
  - Agent: publish, revert, list Versions, get Version, diff, start Draft from Version, discard Draft, Live History.
  - Project Instructions: publish, revert, list Versions, diff.
  - Bulk publish and bulk revert, plus an "Agents behind" summary.
  - All Editor or Owner, all audited.
- **Studio UI.**
  - Publish dialog: note, Instructions Version picker, Draft-vs-Live diff preview.
  - Version history panel with diff viewer.
  - Live History timeline.
  - Revert button with confirmation.
  - Agent list with multi-select and bulk actions.
  - Project Instructions page with history, "N Agents behind", and the bulk dialog after publishing.
  - Playground Instructions picker.

## Testing Decisions

- **Good tests** drive publish, revert and bulk actions through the API and assert on what's Live, which Instructions are served (the `FunctionModel` echo fake shows the Instructions text reaching the model), and what the history and Audit log say. They never assert on table rows.
- **API seam scenarios:**
  - publish → Live; publish → revert → the earlier Version is Live and serves its pinned Instructions;
  - publish, revert, revert walks history correctly; revert with no history is refused;
  - Versions can't be changed (attempts through every write endpoint fail; a direct database update in a single defence-in-depth test is refused);
  - start Draft from a Version; discard Draft; stale Draft save returns 409;
  - Instructions publish moves the Current Version; Instructions revert returns the bulk-revert candidates;
  - bulk publish uses Live config even when the Draft differs, skips never-published Agents, reports per-Agent outcomes, and a forced failure on one Agent leaves the others committed;
  - "Agents behind" counts;
  - Playground with a chosen Instructions Version;
  - Message attribution to Version or Draft;
  - an Audit Event for every action.
- **Concurrency:** two concurrent publishes on one Agent produce consecutive Version numbers with no duplicates (run with real Postgres and parallel requests).
- **Diff:** tested through its interface with AgentConfig pairs covering nested groups, lists (Tags, starter questions) and markdown.
- **Migration:** the migration from spec 04's Instructions field to Draft plus v1 is covered by the migration round-trip test plus a data assertion.
- **Frontend, network seam:** the publish dialog shows the diff and Instructions picker; history and diff views; revert confirmation; bulk dialog selection, badges and the per-Agent result display; "N Agents behind"; the 409 conflict prompt.
- **End-to-end:** publish Instructions v2 → bulk-adopt on one of two Agents → Agent A serves v2 and Agent B is "behind" → revert Agent A → it serves v1 again.
- **Prior art:** spec 04 runtime fakes and Playground tests.

## Out of Scope

- Versioning Documents or the Knowledge Base (ADR-0003).
- Versioning Operational Settings or the Theme (ADR-0009).
- Scheduled publishing, approval workflows or A/B traffic splits between Versions.
- Showing Versions to Visitors (spec 06 serves the Live Version).

## Further Notes

- The Live History revert rule is the subtle part. Make sure it's covered by a table-driven test of action sequences, and keep the rule written down in the module's docstring.
- ADR-0003 is the governing decision. Any change to "bulk publish uses Live config" needs a superseding ADR.
