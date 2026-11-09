# 07: Instructions, Versions and rollout dialog

**Ticket:** `11-07` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** Project Instructions get the new look: the editor and Draft management, a Versions timeline with compare using `Diff`, and the rollout and bulk revert offers in a `Dialog`.

**Blocked by:**
- [11-05: Project frame](05-project-frame.md)

**Status:** done

- [x] The Instructions editor, character count, Draft actions and Publish (the one primary) follow the recipes
- [x] Versions are a timeline with the Current Version badged; any two can be compared and the diff uses `Diff`
- [x] The rollout offer is a `Dialog` with every eligible Agent pre-selected and Draft changes badged; results show succeeded, skipped and failed per Agent
- [x] The Agents-behind summary uses badges instead of plain text
- [x] Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR
- [x] The palette ratchet baseline is lowered to the new count
- [x] Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas
- [x] axe reports zero AA violations on the changed pages in both Appearances
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

Evidence: [11-07-evidence/README.md](11-07-evidence/README.md).
