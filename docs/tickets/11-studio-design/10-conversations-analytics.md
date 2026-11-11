# 10: Conversations and Analytics

**Ticket:** `11-10` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** Conversations becomes a list beside the transcript with pill filters, also shown as the Agent's Conversations view; Analytics shows KPI cards with intervals and the time-series chart in the approved chart style.

**Blocked by:**
- [11-05: Project frame](05-project-frame.md)
- [11-08: Agent page and its four views](08-agent-views.md)

**Status:** done

- [x] Conversations: the list with Agent, Version and date filters and a Visitors/Playground/Both `Segmented`, `Pagination`, and the selected transcript beside it
- [x] Transcripts badge guardrail blocks, show the answering Version, rating and feedback, and fold the Trace under each answer
- [x] The Agent's Conversations view is the same list filtered to that Agent
- [x] Analytics: KPI cards with 95% intervals and n, low samples drawn dashed with a Low sample badge
- [x] Analytics stays a Project section with an Agent filter; each Agent's views offer an "Analytics for this Agent" link that opens it pre-filtered
- [x] The chart uses `chart-1`, a 2px line with area fill, Live markers as labelled dashed rules, the Documents-changed band and note, a crosshair tooltip, and a Table view; never two y-axes
- [x] Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR
- [x] The palette ratchet baseline is lowered to the new count
- [x] Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas
- [x] axe reports zero AA violations on the changed pages in both Appearances
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

Evidence: [11-10-evidence/README.md](11-10-evidence/README.md).
