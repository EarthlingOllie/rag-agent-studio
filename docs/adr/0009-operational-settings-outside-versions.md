# Operational Settings are live, not versioned

Allowed Origins, rate limits and the Token Budget take effect as soon as they are saved, and are not part of an Agent Version. Every change is audit-logged instead. Adding a website or raising a budget during an incident shouldn't require publishing, and shouldn't show up as a new Version that distorts comparisons by Version. Don't "fix" this by folding them into the Version snapshot.
