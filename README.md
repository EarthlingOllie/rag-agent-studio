# Orchestrator handoff (2026-11-05)

Paused at the usage limit after wave 15 of 25. Not for merging.

- `orchestrator/state.md` is the orchestrator memory; its STATUS line has the resume order.
- `orchestrator/plugin/ship.js` launches one ticket: `Workflow({scriptPath: ship.js, args: {now, scratch, localMerge: true, t: {...}}})`. `dispatch.js` is a copy of the graph-orchestrator plugin script.
- `orchestrator/trace/` + `session.mmd` is the dispatch trace (render with the plugin's render-trace.js).
- Uncommitted ticket work was snapshotted to `wip/ticket/<id>-<slug>` branches. Resume each ticket from its `ticket/...` branch, then merge in or cherry-pick from the matching `wip/...` branch.
