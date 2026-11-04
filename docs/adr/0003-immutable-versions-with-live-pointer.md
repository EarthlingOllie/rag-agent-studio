# Immutable Versions with a movable Live pointer; Agent Versions pin Project Instructions

Agents and Project Instructions each have one mutable Draft and an append-only list of immutable, numbered Versions. Publishing an Agent creates a new Version and points Live at it. Reverting only moves the Live pointer back to the Version that was previously Live; it does not copy an old Version forward.

Each Agent Version **pins** one Project Instructions Version. We rejected the alternative, where an Agent always follows the Project's latest Instructions and Messages log both IDs, because pinning makes an Agent Version a single, complete description of behaviour. Comparing Versions then has one dimension, and reverting an Agent also restores the Instructions it ran with. The cost of pinning is that new Instructions reach Agents only when they are republished, so the Studio offers bulk publish and bulk revert across a Project's Agents.

Documents are deliberately *not* versioned: the Knowledge Base is live and shared, which is a known confounder when comparing Versions.
