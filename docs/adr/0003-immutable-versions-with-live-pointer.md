# Immutable Versions with a movable Live Version pointer

Agents and Project Instructions each have one mutable Draft and an append-only list of immutable, numbered Versions. Publishing creates a new Version and points Live at it. Reverting only moves the Live pointer back. It does not copy an old Version forward. That way every logged Message references the exact Version that served it, so metrics compared by Version stay honest. Documents are deliberately *not* versioned: the Knowledge Base is live and shared, which is a known confounder when comparing Versions.
